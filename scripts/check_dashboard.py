"""Validate actual generated payload and extract executable JS for node --check."""
import json
import re
import sys
from pathlib import Path
html=Path(sys.argv[1]).read_text()
payload=json.loads(re.search(r'<script id="payload" type="application/json">(.*?)</script>',html,re.S)[1])
assert payload['hotspots']
assert payload['discovery_status'] in ('scored','missing_data')
scripts=re.findall(r'<script>(.*?)</script>',html,re.S)
assert scripts
Path('/tmp/aiba-dashboard.js').write_text('\n'.join(scripts))
print('Dashboard payload and script extracted successfully')
