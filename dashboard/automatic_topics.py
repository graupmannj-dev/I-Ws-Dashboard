"""Automatic, persistent, source-grounded *analytical topic* discovery.

Clusters documents by informative lexical/semantic-proxy similarity, source
domain and reported subject geography. Does NOT merge actual events or infer
corroboration, intent, location, or a threat level.

Uses a bounded inverted index of document terms (no third-party model, network,
secrets or API expense). Original documents and fragments remain nested. The
append-only assignment ledger stabilizes topic IDs across re-collections.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import datetime as dt
import hashlib
import math
import re

try:
    from .evidence_facets import facets, qualified_metric
    from .topic_families import COUNTRIES, region_from_title
except ImportError:
    from evidence_facets import facets, qualified_metric
    from topic_families import COUNTRIES, region_from_title
try:
    from .topic_semantics import LocalTopicEmbeddings, normalized_terms, SCHEMA as EMBEDDING_SCHEMA
except ImportError:
    from topic_semantics import LocalTopicEmbeddings, normalized_terms, SCHEMA as EMBEDDING_SCHEMA


SCHEMA = "aiba.automatic-analytical-topics.v1"
MAX_DOCS_PER_UPDATE = 6000
MAX_STORED_DOCS = 60000
MAX_TOPIC_SOURCES = 550
MAX_TOPIC_NOTICES = 160
MAX_FRAGMENTS_PER_DOC = 130
MIN_SIMILARITY = 0.64
MIN_SHARED_TERMS = 2
_MAX_CANDIDATES = 300
GEO_NAMES = sorted(COUNTRIES, key=len, reverse=True)
COUNTRY_RE = re.compile(r"(?<!\w)(?:"+"|".join(re.escape(x) for x in GEO_NAMES)+r")(?!\w)", re.I)
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?",re.I)
NOISE = frozenset((
    "a an and or the to of for from in on at by under near across off during"
    " with about into after before has have had is are was were be as its it"
    " this that these those now new says say said report reports reported reporting"
    " latest officials official notice notices warning warnings advisory advisories"
    " bulletin bulletins alert alerts update updates situation statement published"
    " november december january february march april may june july august september"
    " october monday tuesday wednesday thursday friday saturday sunday"
    " year years day days month months today tomorrow monday through till utc"
    " us usa u s america american united states north south east west"
    " level caution exercise increased precautions reconsider travel not do"
    " airport airports tfr faa nasa norad ioda detected country data"
    " synthetic fixture test example source sample document led beh"
).split())
GENERIC = frozenset((
    "security military forces operations activity incident event events "
    "restricted restriction area areas maritime shipping ship vessel vessels "
    "aircraft flight flights traffic government official closure closed"
).split())
ALIASES = {
    "exercises":"exercise","exercising":"exercise",
    "fired":"firing","fires":"firing","gunfire":"firing",
    "closures":"closure","closing":"closure","shutdowns":"shutdown",
    "ships":"ship","vessels":"vessel","vessel":"vessel",
    "strikes":"strike","attacks":"attack","attacked":"attack",
    "invasions":"invasion","invading":"invasion","blockades":"blockade",
    "disruptions":"disruption","outages":"outage","stoppages":"stop",
    "agreements":"agreement","routes":"route",
    "russian":"russia","iranian":"iran","danish":"denmark",
    "chinese":"china","taiwanese":"taiwan",
}
DOMAIN_HINTS = {
    "maritime":frozenset(("ship","vessel","shipping","port","naval","maritime","sea","strait","ferry","tanker","cruise","hormuz")),
    "aviation":frozenset(("flight","aircraft","airport","airspace","aviation","freighter","tfr","faa")),
    "network":frozenset(("internet","network","connectivity","outage","bgp","dns","routing","cyber")),
}
SOURCE_DOMAINS = {
    "maritime_restriction":"maritime",
    "airspace_restriction":"aviation",
    "aviation_operations":"aviation",
    "internet_reachability":"network",
    "protective_notice":"advisory",
    "market_expectation":"generic",
    "commercial_media":"generic",
}
UTC=dt.timezone.utc


def _date(s):
    try:
        d=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
        if not d.tzinfo or d.utcoffset() is None:
            return None
        return d.astimezone(UTC)
    except (ValueError,TypeError,OverflowError):
        return None


def _raw_tokens(title):
    text=title.casefold().replace("–"," ").replace("—"," ").replace("-"," ")
    # Preserve country mentions as *subject* metadata, not event geocoding.
    return [ALIASES.get(t,t) for t in TOKEN_RE.findall(text)]


def _subject_geo(row):
    geo=row.get("geography_key") or ""
    if isinstance(geo,str) and geo.lower().startswith("country:"):
        code=geo.split(":",1)[1].strip().upper()
        if re.fullmatch("[A-Z]{2}",code):
            return frozenset(("iso:"+code,))
    title=row.get("title") or ""
    # Some source adapters expose the target country only in the title.
    # A source-declared "country FI" code is subject context, never an event
    # geolocation. Different country targets must not be clustered together.
    code=re.search(r"\bcountry\s+([A-Za-z]{2})\b",title,re.I)
    if code:
        return frozenset(("iso:"+code.group(1).upper(),))
    countries={c.casefold() for c in COUNTRY_RE.findall(title)}
    if re.search(r"\b(?:U\.S\.|USA|United States)\b",title,re.I):
        countries.add("united states")
    # This is *mentioned subject* geography, not an event point or attribution.
    return frozenset(countries)


def _terms(row):
    title=row.get("title") or ""
    country_terms={t for country in _subject_geo(row) for t in country.split()}
    return Counter(t for t in _raw_tokens(title)
                   if len(t)>=3 and t not in NOISE and not t.isdigit()
                   and t not in country_terms and len(t)<32)


def _domain(row):
    dom=SOURCE_DOMAINS.get(row.get("source_family"),"generic")
    if dom not in ("generic","advisory"):
        return dom
    tokens=set(_raw_tokens(row.get("title") or ""))
    scores={domain:len(tokens & terms) for domain,terms in DOMAIN_HINTS.items()}
    top=max(scores,key=lambda k:scores[k])
    return top if scores[top]>=2 else dom


def _doc_key(row):
    # One official message can yield several shapes and validity fragments.
    # A generic API URL (IODA) must NOT merge unrelated country observations.
    if row.get("source_family") in ("internet_reachability","aviation_operations"):
        key=row["information_root"]
    else:
        key=row.get("source_url") or row["information_root"]
    return hashlib.sha256((str(row.get("source_family"))+"|"+key).encode()).hexdigest()[:28]


def documents(rows):
    by_doc=defaultdict(list)
    for row in rows:
        if not isinstance(row,dict) or not row.get("information_root") or not row.get("id"):
            continue
        if not _date(row.get("first_observed_at")):
            continue
        by_doc[_doc_key(row)].append(row)
    result=[]
    for key,fragments in by_doc.items():
        fragments.sort(key=lambda r:(r["first_observed_at"],r["id"]))
        representative=fragments[0]
        # Select most descriptive title if a provider occasionally changes it.
        title=max((r.get("title") or "" for r in fragments),key=len)
        representative={**representative,"title":title}
        result.append({
            "key":key,"rows":fragments,"title":title,
            "first":fragments[0]["first_observed_at"],
            "latest":fragments[-1]["first_observed_at"],
            "source_family":representative.get("source_family") or "",
            "source_url":representative.get("source_url") or "",
            "terms":_terms(representative),
            "geo":_subject_geo(representative),
            "domain":_domain(representative),
            "publisher":representative.get("provider") or "",
        })
    return sorted(result,key=lambda d:(d["first"],d["key"]))


def _similar(doc,seed):
    if doc["domain"]!=seed["domain"]:
        return (0.0, [])
    # Do not use advisory boilerplate to create topic-wide false positives.
    if doc["domain"]=="advisory":
        return (0.0,[])
    a=doc["terms"]
    b=Counter(seed["terms"])
    shared=set(a)&set(b)
    meaningful=[t for t in shared if t not in GENERIC]
    if len(meaningful)<MIN_SHARED_TERMS:
        return (0.0,[])
    ga=set(doc["geo"]);gb=set(seed["geo"])
    if ga and gb and ga.isdisjoint(gb):
        return (0.0,[])
    # Inverse generic-frequency weights: distinctive words dominate.
    def weight(t):
        return 0.35 if t in GENERIC else 1.0
    overlap=sum(min(a[t],b[t])*weight(t) for t in shared)
    den=sum(v*weight(t) for t,v in a.items())+sum(v*weight(t) for t,v in b.items())
    lexical=2*overlap/den if den else 0
    boost=0.05 if ga and gb and ga.intersection(gb) else 0
    return (min(1.0,lexical+boost),sorted(meaningful))


# Broad functional roles are linguistic safeguards, not a country/event
# allowlist. Incompatible explicit roles never merge automatically.
ACTIVITY_ROLES = {
    "blockade":frozenset(("blockade","interdict","embargo","interdiction")),
    "kinetic":frozenset(("attack","strike","bomb","explosion","assault","missile")),
    "agreement":frozenset(("agreement","accord","negotiation","talks","treaty","deal")),
    "exercise":frozenset(("exercise","training","drill","firing","gunnery")),
    "outage":frozenset(("outage","blackout","disruption","offline")),
    "closure":frozenset(("closure","closed","restrict","restriction")),
    "movement":frozenset(("movement","deployment","diversion","rerouting","shipment")),
    "seizure":frozenset(("seizure","captured","capture","occupy","occupation")),
}
HYBRID_AUTO_THRESHOLD=0.68
HYBRID_SUBJECT_THRESHOLD=0.55
TEMPLATE_WORDS=frozenset((
    "faa tfr temporary restrictions restricted restriction notice source "
    "advisory bulletin status official airport flight airspace country "
    "connectivity anomaly detected news report latest update security"
).split())
MAX_SEMANTIC_SEEDS=2800
BROAD_SUBJECT_WORDS=frozenset((
    "ship shipping cargo freight freighter maritime naval sea ocean vessel port "
    "traffic airspace aircraft airport flight network internet mobile "
    "official bulletin warning source operations report halt announced "
    "temporary state government"
).split())


def _named_subjects(title):
    # Candidate named subjects only; they are not event/geolocation claims.
    words=re.findall(r"\b[A-Z][a-z]{3,}\b",title or "")
    result=set()
    for word in words:
        result.update(normalized_terms(word))
    return result-BROAD_SUBJECT_WORDS-GENERIC-NOISE



def _roles(title):
    tokens=set(normalized_terms(title))
    return frozenset(name for name,items in ACTIVITY_ROLES.items()
                     if tokens&items)


def _reasoning(doc,seed,metric):
    """Hard gates prevent false thematic joins before any soft similarity."""
    if doc["domain"]!=seed["domain"]:
        return None
    if doc["domain"]=="advisory":
        return None
    ga=set(doc["geo"]);gb=set(seed.get("geo") or [])
    if ga and gb and ga.isdisjoint(gb):
        return None
    doc_roles=_roles(doc["title"])
    seed_roles=_roles(seed["title"])
    if doc_roles and seed_roles and doc_roles.isdisjoint(seed_roles):
        return None
    # Similarity alone is insufficient where only template boilerplate remains.
    a=set(normalized_terms(doc["title"]))-GENERIC-NOISE
    z=set(normalized_terms(seed["title"]))-GENERIC-NOISE
    shared=(a&z)-TEMPLATE_WORDS
    legacy,legacy_terms=_similar(doc,seed)
    same_subject=bool(ga and gb and ga.intersection(gb))
    shared_roles=bool(doc_roles and seed_roles and not doc_roles.isdisjoint(seed_roles))
    # Existing accepted high-precision lexical matches remain available.
    legacy_ok=legacy>=MIN_SIMILARITY
    hybrid_ok=(metric["score"]>=HYBRID_AUTO_THRESHOLD and len(shared)>=2)
    # This condition can recognize paraphrases when two different phrasings
    # share a reported entity and general activity, but it must not unite
    # all reporting about that country.
    # Shared non-template subject/entity terms and a compatible activity
    # allow paraphrased reports across different original publishers. A
    # standalone country or generic activity word does NOT suffice.
    role_tokens=set().union(*ACTIVITY_ROLES.values())
    shared_named=_named_subjects(doc["title"])&_named_subjects(seed["title"])
    # Short articles and market contracts often have too little corpus
    # context for SVD. Strong role + shared named entity + several mapped
    # substantive terms is therefore an independent high-precision route.
    paraphrase_ok=(
        shared_roles and len(shared)>=2 and bool(shared_named)
        and (metric["score"]>=0.25 or legacy>=0.35)
    ) or (
        metric["score"]>=HYBRID_SUBJECT_THRESHOLD
        and same_subject and shared_roles and len(shared)>=2
        and bool((shared-role_tokens)-BROAD_SUBJECT_WORDS)
        and (metric["latent_cosine"] or 0)>=0.67
    )
    if not (legacy_ok or hybrid_ok or paraphrase_ok):
        return None
    if len(shared)<2 and not paraphrase_ok and not legacy_ok:
        return None
    return {
        "method":EMBEDDING_SCHEMA if hybrid_ok or paraphrase_ok else "legacy_sparse_v1",
        "score":round(max(metric["score"],legacy),4),
        "raw_text_similarity":metric["tfidf_cosine"],
        "latent_semantic_similarity":metric["latent_cosine"],
        "shared_subject_terms":sorted(shared)[:12],
        "shared_named_subjects":sorted(_named_subjects(doc["title"])&_named_subjects(seed["title"]))[:8],
        "shared_activity_roles":sorted(doc_roles & seed_roles),
        "subject_geography_compatible":not (ga and gb and ga.isdisjoint(gb)),
        "same_source_document":False,
        "same_incident_proven":False,
        "independent_corroboration_proven":False,
        "review_status":"unreviewed_automatic_topic_match",
    }


def _seed(doc):
    return {
        "terms":dict(doc["terms"]), "geo":sorted(doc["geo"]),
        "domain":doc["domain"], "source_family":doc["source_family"],
        "title":doc["title"][:240], "publisher":doc["publisher"][:100],
        "key":doc["key"],
    }


def _valid_prior(prior):
    if not isinstance(prior,dict) or prior.get("schema")!=SCHEMA:
        return {"schema":SCHEMA,"groups":{},"assignments":{}}
    groups=prior.get("groups")
    assignments=prior.get("assignments")
    if not isinstance(groups,dict) or not isinstance(assignments,dict):
        raise ValueError("Malformed persistent auto-topic ledger")
    if len(assignments)>MAX_STORED_DOCS:
        raise ValueError("Persistent auto-topic ledger needs repartitioning")
    return deepcopy(prior)


def assign(rows, prior=None):
    """Autonomously attach source documents to long-lived, unreviewed themes.

    Stable existing membership always wins. For *new* documents, hybrid local
    embeddings broaden candidate retrieval, while explicit source geography,
    domain, activity-role and boilerplate gates control false joins.
    """
    out=_valid_prior(prior)
    groups=out["groups"]
    assignments=out["assignments"]
    explanations=out.setdefault("assignment_explanations",{})
    docs=documents(rows)
    if len(docs)>MAX_DOCS_PER_UPDATE:
        docs=docs[-MAX_DOCS_PER_UPDATE:]
        out["input_truncated"]=True
    else:
        out["input_truncated"]=False
    inverted=defaultdict(set)
    for gid,g in groups.items():
        for term in (g.get("seed") or {}).get("terms",{}):
            if term not in GENERIC:
                inverted[term].add(gid)

    # Train local latent-semantic vectors once per batch, using persisted topic
    # seed titles plus fresh source titles. Stable assignments do NOT depend
    # on subsequent embeddings or models being available.
    ordered=sorted(groups,key=lambda gid:(
        groups[gid].get("last_document_at") or groups[gid].get("first_document_at") or "",
        gid),reverse=True)
    existing_semantic_seeds=ordered[:MAX_SEMANTIC_SEEDS]
    seed_positions={gid:i for i,gid in enumerate(existing_semantic_seeds)}
    titles=[groups[gid]["seed"]["title"] for gid in existing_semantic_seeds]
    start_docs=len(titles)
    titles.extend(doc["title"] for doc in docs)
    model=LocalTopicEmbeddings(titles)
    out["semantic_seed_index_limited"]=len(groups)>len(existing_semantic_seeds)
    newly_added=[]
    new_count=0

    for offset,doc in enumerate(docs):
        key=doc["key"]
        if key in assignments:
            if assignments[key] not in groups:
                raise ValueError("Topic ledger references missing stable group")
            continue
        if doc["domain"]=="advisory" or len(set(doc["terms"])-GENERIC)<MIN_SHARED_TERMS:
            continue
        position=start_docs+offset
        # Inverted lookups preserve older archived seeds beyond the bounded
        # dense index. Top latent nearest-neighbors discover unfamiliar
        # paraphrases with no requirement for the exact same title.
        candidate_counts=Counter(gid for term in doc["terms"] if term not in GENERIC
                                 for gid in inverted[term])
        candidates=set(gid for gid,n in
                       candidate_counts.most_common(_MAX_CANDIDATES) if n>=1)
        for seed_idx in model.candidates(position,len(existing_semantic_seeds),top=36):
            candidates.add(existing_semantic_seeds[seed_idx])
        # New groups created earlier this same batch can also receive members.
        candidates.update(newly_added[-120:])
        best=None
        for gid in sorted(candidates):
            g=groups.get(gid)
            if not g:
                continue
            seed=g["seed"]
            # Cheap hard gates precede potentially expensive similarities.
            if doc["domain"]!=seed["domain"]:
                continue
            ga=set(doc["geo"]);gb=set(seed.get("geo",[]))
            if ga and gb and ga.isdisjoint(gb):
                continue
            a=_roles(doc["title"]);z=_roles(seed["title"])
            if a and z and a.isdisjoint(z):
                continue
            if gid in seed_positions:
                metrics=model.pair(position,seed_positions[gid])
            else:
                oldscore,_=_similar(doc,seed)
                metrics={"score":oldscore,"tfidf_cosine":oldscore,
                         "latent_cosine":None}
            rationale=_reasoning(doc,seed,metrics)
            if rationale is None:
                continue
            quality=(rationale["score"],gid)
            if best is None or quality>(best[0],best[1]):
                best=(quality[0],gid,rationale)
        if best is None:
            gid="family:"+hashlib.sha256(("auto_topic:v1:"+key).encode()).hexdigest()[:20]
            if gid in groups and groups[gid]["seed"]["key"]!=key:
                raise ValueError("Topic ID hash collision")
            groups[gid]={
                "seed":_seed(doc),"first_document_at":doc["first"],
                "last_document_at":doc["first"],
                "source":"hybrid_local_topic_embedding_v2",
                "matched_document_count":0,
            }
            seed_positions[gid]=position
            newly_added.append(gid)
            for term in doc["terms"]:
                if term not in GENERIC:
                    inverted[term].add(gid)
            explanation={
                "method":"new_analytical_theme","score":None,
                "shared_subject_terms":[],"shared_activity_roles":[],
                "same_incident_proven":False,
                "independent_corroboration_proven":False,
                "review_status":"unreviewed_automatic_topic_seed",
            }
        else:
            gid=best[1]
            explanation=best[2]
            groups[gid]["last_document_at"]=max(
                groups[gid].get("last_document_at") or doc["first"],doc["first"])
        assignments[key]=gid
        explanations[key]=explanation
        groups[gid]["matched_document_count"]+=1
        new_count+=1
        if len(assignments)>MAX_STORED_DOCS:
            raise ValueError("Topic assignment capacity; do not silently discard history")
    out["new_document_assignments"]=new_count
    out["total_document_assignments"]=len(assignments)
    out["total_stable_topics"]=len(groups)
    out["automatic_similarity_method"]="hybrid_sparse_char_ngram_lsa_v2"
    return out


def _title(seed,docs):
    counts=Counter()
    if len(docs)>1:
        for doc in docs:
            counts.update(set(doc["terms"])-GENERIC)
    seed_order={t:i for i,t in enumerate(_raw_tokens(seed.get("title","")))}
    shared=sorted((t for t,n in counts.items() if n>=2),
                  key=lambda t:(-counts[t],seed_order.get(t,999),t))
    if len(shared)<2:
        shared=[t for t in seed.get("terms",{}) if t not in GENERIC]
    area=sorted(seed.get("geo",[]))
    prefix=(", ".join(area[:2])+" · ") if area else ""
    # Explicit machine-generated topic label, not an analyst verified claim.
    return (prefix+" / ".join(shared[:4]))[:170] or seed.get("title","Unlabeled analytical topic")


def build_topics(rows, now, source_health=None, prior=None, exclude_roots=()):
    """Build display families from persisted or inferred document assignments."""
    index=assign(rows,prior)
    # region_from_title imported above for both module and script execution.
    skip=set(exclude_roots)
    docs=documents([row for row in rows if row.get("information_root") not in skip])
    by_gid=defaultdict(list)
    for doc in docs:
        gid=index["assignments"].get(doc["key"])
        if gid:
            by_gid[gid].append(doc)
    topics=[]
    covered=set()
    for gid,items in by_gid.items():
        # Only expose a shared theme with >=2 source documents. Isolated
        # observations remain visible in the ordinary evidence queue.
        historic_count=index["groups"][gid]["matched_document_count"]
        if len(items)<2 and historic_count<2:
            continue
        # A long-lived topic stays visible when the bounded public snapshot
        # contains one recent member but older documents are archived.
        seed=index["groups"][gid]["seed"]
        raw=[r for doc in items for r in doc["rows"]]
        newest=max(_date(r["first_observed_at"]) for r in raw)
        oldest=min(_date(r["first_observed_at"]) for r in raw)
        if newest>now:
            continue
        age=now-newest
        lifecycle="emerging" if age<=dt.timedelta(hours=36) else (
            "monitoring" if age<=dt.timedelta(days=14) else "quiet")
        notices=[]
        for doc in items:
            fragments=sorted(doc["rows"],key=lambda x:(x["first_observed_at"],x["id"]),reverse=True)
            intervals=sorted(set(
                (r.get("scheduled_valid_from") or "",r.get("scheduled_valid_until") or "")
                for r in fragments if r.get("scheduled_valid_from") or r.get("scheduled_valid_until")
            ))
            notices.append({
                "id":"notice:"+doc["key"],
                "title":doc["title"],
                "source_url":doc["source_url"],
                "area_label":region_from_title(doc["title"]) if
                    doc["source_family"]=="maritime_restriction" else
                    "Source subject area not independently verified",
                "first_observed_at":doc["first"],
                "last_new_observation_at":doc["latest"],
                "source_record_count":len(fragments),
                "information_root_count":len({r["information_root"] for r in fragments}),
                "publisher_names":sorted({r["provider"] for r in fragments if r.get("provider")}),
                "grouping_explanation":index.get("assignment_explanations",{}).get(
                    doc["key"],{
                        "method":"existing_persistent_assignment",
                        "score":None,"review_status":"not_automatically_adjudicated",
                    }),
                "validity_windows":[{"from":a or None,"until":b or None} for a,b in intervals[:30]],
                "validity_windows_truncated":len(intervals)>30,
                "records":fragments[:MAX_FRAGMENTS_PER_DOC],
                "records_truncated":len(fragments)>MAX_FRAGMENTS_PER_DOC,
            })
        notices.sort(key=lambda n:(n["last_new_observation_at"],n["id"]),reverse=True)
        roots={r["information_root"] for r in raw}
        # All records of a root must belong to this family before its smaller
        # card can disappear from triage. Never hide ungrouped source records.
        by_root=defaultdict(set)
        all_by_root=defaultdict(set)
        for r in rows:
            all_by_root[r["information_root"]].add(r["id"])
        for r in raw:
            by_root[r["information_root"]].add(r["id"])
        covered.update(root for root in roots if by_root[root]==all_by_root[root])
        publishers=sorted({doc["publisher"] for doc in items if doc["publisher"]})
        topics.append({
            "id":gid,"kind":"analytical_topic_family",
            "title":_title(seed,items),
            "activity":"automatically_discovered_shared_subject",
            "country":", ".join(seed.get("geo",[])) or None,
            "state":lifecycle,"new_activity":lifecycle=="emerging",
            "first_observed_at":oldest.isoformat(),
            "last_observed_at":newest.isoformat(),
            "notice_count":len(items),
            "source_record_count":len(raw),
            "information_root_count":len(roots),
            "source_families":sorted({r["source_family"] for r in raw}),
            "providers":publishers,
            "case_hints":sorted({r["case_hint"] for r in raw if r.get("case_hint")}),
            "geography_label":"Shared *mentioned* geographic subjects" if seed.get("geo") else None,
            "geography_precision":"textual_subject_not_event_location",
            "map_eligible":False,"source_independence_established":False,
            "event_occurrence_verified":False,"warning_approved":False,
            "corroboration":{
                "status":"automatic_topic_similarity_not_independent_confirmation",
                "independent_roots":None,"notice_count":len(items),
                "issuer_count":len(publishers),
            },
            "anomaly_metric":qualified_metric(raw),
            "evidence_facets":facets(raw,source_health),
            "notice_groups":notices[:MAX_TOPIC_NOTICES],
            "notice_groups_truncated":len(notices)>MAX_TOPIC_NOTICES,
            "sources":raw[:MAX_TOPIC_SOURCES],
            "sources_truncated":len(raw)>MAX_TOPIC_SOURCES,
            "automatic_grouping":{
                "method":"hybrid_sparse_char_ngram_lsa_v2",
                "threshold":HYBRID_AUTO_THRESHOLD,
                "scoring_method":EMBEDDING_SCHEMA,
                "seed_document":seed["key"],
                "manual_curation_required":False,
                "event_identity_assumed":False,
                "membership_review_status":"unreviewed_automatic_theme",
                "public_documents_displayed":len(items),
                "historical_assigned_documents":historic_count,
                "older_members_not_loaded":historic_count>len(items),
            },
            "reason":"Automatic locally embedded source theme with explicit source-domain, activity-role and reported-subject safeguards. Documents can concern different occurrences; clustering neither confirms events nor independent corroboration.",
        })
    return topics,covered,index
