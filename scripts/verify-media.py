"""Local-only verification against an explicit sample manifest; never writes originals."""
import argparse
from fractions import Fraction
import hashlib
import json
import subprocess
from pathlib import Path
from mvideo.config import Settings
from mvideo.database import Database
from mvideo.library import Library
from mvideo.playback import Playback
from mvideo.parsing import parse_filename

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--manifest',type=Path,required=True)
parser.add_argument('--output',type=Path,default=Path('output/media-verification'))
args=parser.parse_args()
root=args.root.resolve()
settings=Settings(root,args.output)
settings.prepare();database=Database(settings.state/'library.sqlite3');library=Library(settings,database)
playback=Playback(settings,library)
samples=json.loads(args.manifest.read_text())
seen=set();results=[]
for sample in samples:
    if sample['extension'] in seen:continue
    seen.add(sample['extension'])
    path=root/sample['file'];stat=path.stat();parsed=parse_filename(path.name)
    identity=hashlib.sha256(path.name.encode()).hexdigest()[:32]
    with database.connect() as db:
        db.execute('INSERT OR REPLACE INTO videos VALUES(?,?,?,?,?,?,?,?,?,?,?,1)',(identity,path.name,stat.st_size,stat.st_mtime_ns,parsed['artist'],parsed['title'],parsed['year'],parsed['raw_name'],json.dumps(parsed['warnings']),json.dumps(sample['probe']),None))
    output=path
    if sample['plan']!='direct':
        output=settings.state/'playback'/(playback.cache_key(library.get(identity))+'.mp4')
        if not output.exists():playback.convert(identity,output,sample['plan'])
    probe=library.probe(output)
    duration=float(probe['format']['duration'])
    def display_ratio(info):
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        sar=video.get('sample_aspect_ratio') or '1:1'
        if sar in ('N/A','0:1'): sar='1:1'
        return video['width']/video['height']*float(Fraction(sar.replace(':','/')))
    aspect_ok=abs(display_ratio(probe)-display_ratio(sample['probe']))<.01
    checks=[]
    for position in [0,duration/2,max(0,duration-3)]:
        r=subprocess.run([settings.ffmpeg,'-v','error','-ss',str(position),'-i',str(output),'-t','1','-map','0:v:0','-map','0:a:0?','-f','null','-'],capture_output=True,timeout=60)
        checks.append(r.returncode==0)
    after=path.stat()
    result={'file':path.name,'mode':sample['plan'],'aspect_ratio_preserved':aspect_ok,'seek_decode_start_middle_end':checks,'original_unchanged':(stat.st_size,stat.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'output':probe}
    results.append(result)
    (args.output/'results.json').write_text(json.dumps(results,indent=2))
    print(path.suffix, sample['plan'],checks,'aspect',aspect_ok,'unchanged',result['original_unchanged'],flush=True)
playback.close()

assert all(all(r['seek_decode_start_middle_end']) and r['original_unchanged'] and r['aspect_ratio_preserved'] for r in results), 'Media verification failed'
