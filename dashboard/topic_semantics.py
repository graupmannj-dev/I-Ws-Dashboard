"""Local, bounded hybrid text embeddings for AIBA analytical-family discovery.

Word/bigram + character-ngram TF-IDF features, plus a deterministic truncated
latent semantic analysis (LSA) projection trained on the observed source titles.
No external model inference, API calls, tokens, PII export, or network required.

Cosine similarity is *topic similarity* and is never a probability that two
reports refer to one incident or independently corroborate one another.
"""
from __future__ import annotations

from collections import Counter
import math
import re
import unicodedata
import zlib

try:
    import numpy as np
    from scipy import sparse
except ImportError:
    np=None
    sparse=None


SCHEMA = "aiba.hybrid-local-title-embedding.v1"
FEATURE_COUNT = 8192
EMBEDDING_DIM = 24
SEED = 75
MAX_TITLES = 8000
COMMON = frozenset((
    "a an and the for from into with during after before of in on at to is"
    " are was were has have had as by it this that new latest reports says"
    " said official source data bulletin update warning advisories notice"
    " november december january february march april may june july august"
    " september october monday tuesday wednesday thursday friday saturday sunday"
    " utc today tomorrow through until"
).split())
ALIAS = {
    "ships":"ship","vessels":"ship","vessel":"ship","freighters":"ship",
    "freighter":"ship","tankers":"tanker",
    "blockading":"blockade","blockaded":"blockade","blockades":"blockade",
    "interdiction":"blockade","interdict":"blockade","intercepting":"blockade",
    "embargo":"blockade","embargoes":"blockade",
    "attacks":"attack","strikes":"attack","struck":"attack","hit":"attack",
    "hitting":"attack","assault":"attack",
    "exercises":"exercise","drills":"exercise","training":"exercise",
    "manoeuvres":"exercise","maneuvers":"exercise",
    "outages":"outage","blackouts":"outage","blackout":"outage",
    "disconnected":"outage","disruptions":"outage",
    "communications":"network","telecom":"network","telecommunications":"network",
    "cellular":"network","internet":"network",
    "freight":"cargo","shipments":"cargo","goods":"cargo",
    "closure":"closure","closures":"closure","closing":"closure",
    "agreements":"agreement","accord":"agreement","deal":"agreement","deals":"agreement",
    "negotiations":"negotiation","talks":"negotiation",
    "iranian":"iran","syrian":"syria","russian":"russia","chinese":"china",
    "danish":"denmark","taiwanese":"taiwan","ukrainian":"ukraine",
    "movements":"movement","deployments":"deployment",
}


def normalized_terms(title):
    s=unicodedata.normalize("NFKD",str(title).casefold())
    s="".join(c for c in s if not unicodedata.combining(c))
    s=s.replace("–"," ").replace("—"," ")
    tokens=re.findall(r"[a-z]+",s)
    return [ALIAS.get(t,t) for t in tokens if len(t)>=3 and t not in COMMON]


def _features(title):
    tokens=normalized_terms(title)[:90]
    feats=Counter()
    for token in tokens:
        feats["w:"+token]+=1.35
        if len(token)>4:
            for n in (3,4):
                for i in range(len(token)-n+1):
                    feats["c:"+token[i:i+n]]+=0.09
    for a,b in zip(tokens,tokens[1:]):
        feats["b:"+a+":"+b]+=0.75
    return feats


def _hash(text):
    # Explicit stable hash, never Python hash randomization.
    return zlib.crc32(text.encode("utf-8"))%FEATURE_COUNT


def _matrix(titles):
    rows=[];cols=[];vals=[]
    for i,title in enumerate(titles):
        counts=Counter()
        for feature,weight in _features(title).items():
            counts[_hash(feature)]+=weight
        for col,value in counts.items():
            rows.append(i);cols.append(col);vals.append(value)
    x=sparse.csr_matrix((np.asarray(vals,dtype=np.float32),(rows,cols)),
                       shape=(len(titles),FEATURE_COUNT),dtype=np.float32)
    if not titles:
        return x
    df=np.diff(x.tocsc().indptr)
    idf=(np.log((1+len(titles))/(1+df))+1).astype(np.float32)
    x=x.multiply(idf).tocsr()
    norms=np.sqrt(np.asarray(x.multiply(x).sum(axis=1)).reshape(-1))
    inv=np.divide(1,norms,out=np.zeros_like(norms),where=norms>1e-10)
    return sparse.diags(inv.astype(np.float32))@x


def _latent(x):
    n,d=x.shape
    if n<8 or x.nnz<25:
        return None
    k=min(EMBEDDING_DIM,n-2)
    if k<2:
        return None
    # Randomized subspace iteration is deterministic and does not download
    # third-party weights. It learns shared document context from this corpus.
    rng=np.random.default_rng(SEED)
    sketch=rng.standard_normal((d,k+6)).astype(np.float32)
    y=x@sketch
    for _ in range(2):
        y=x@(x.T@y)
    q,_=np.linalg.qr(y,mode="reduced")
    b=np.asarray(q.T@x,dtype=np.float32)
    small_u,s,_=np.linalg.svd(b,full_matrices=False)
    z=(q@small_u[:,:k])*s[:k]
    norms=np.linalg.norm(z,axis=1,keepdims=True)
    return np.divide(z,norms,out=np.zeros_like(z),where=norms>1e-10).astype(np.float32)


class LocalTopicEmbeddings:
    def __init__(self,titles):
        if len(titles)>MAX_TITLES:
            raise ValueError("Embedding corpus too large; repartition explicitly")
        self.count=len(titles)
        self.fallback=None
        self.latent=None
        if np is None or sparse is None:
            # Essential operational collectors remain functional even if
            # package resolution fails. This is a *degraded sparse-only*
            # mode and is surfaced in the archive's model diagnostics.
            vectors=[_features(title) for title in titles]
            df=Counter(k for v in vectors for k in v)
            idf={k:math.log((len(vectors)+1)/(n+1))+1 for k,n in df.items()}
            self.fallback=[]
            for features in vectors:
                weighted={k:val*idf[k] for k,val in features.items()}
                norm=math.sqrt(sum(x*x for x in weighted.values())) or 1
                self.fallback.append({k:v/norm for k,v in weighted.items()})
            self.matrix=None
        else:
            self.matrix=_matrix(titles)
            self.latent=_latent(self.matrix)

    def _simple_cosine(self,a,b):
        x=self.fallback[a];y=self.fallback[b]
        if len(x)>len(y):x,y=y,x
        return max(0,min(1,sum(v*y.get(k,0) for k,v in x.items())))

    def candidates(self,i,seed_count,top=32):
        if not seed_count:return []
        if self.fallback is not None:
            scores=[self._simple_cosine(i,j) for j in range(seed_count)]
            return sorted(range(seed_count),key=lambda j:(-scores[j],j))[:top]
        if self.latent is not None:
            sims=self.latent[:seed_count]@self.latent[i]
        else:
            sims=(self.matrix[:seed_count]@self.matrix[i].T).toarray().reshape(-1)
        if len(sims)<=top:
            inds=np.arange(len(sims))
        else:
            inds=np.argpartition(-sims,top-1)[:top]
        return [int(k) for k in sorted(inds,key=lambda k:(-float(sims[k]),int(k)))]

    def pair(self,a,b):
        if self.fallback is not None:
            tfidf=self._simple_cosine(a,b)
            latent=None
        else:
            tfidf=float((self.matrix[a]@self.matrix[b].T).toarray()[0,0])
            latent=(float(np.dot(self.latent[a],self.latent[b]))
                    if self.latent is not None else None)
        tfidf=max(0,min(1,tfidf))
        if latent is not None:
            latent=max(0,min(1,latent))
        score=(0.64*tfidf+0.36*latent) if latent is not None else tfidf
        return {
            "score":round(float(score),4),
            "tfidf_cosine":round(tfidf,4),
            "latent_cosine":round(latent,4) if latent is not None else None,
            "embedding_method":SCHEMA if self.fallback is None
                else "aiba.local-sparse-degraded.v1",
            "latent_dimensions":int(self.latent.shape[1]) if self.latent is not None else 0,
        }
