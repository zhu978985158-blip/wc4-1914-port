"""Read-only audit and isolated candidate generation, not an APK release builder."""
import argparse
import json, struct, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'inputs/base.apk'
SOURCE=ROOT/'inputs/source.apk'

def rows(z,name): return json.loads(z.read('assets/json/'+name+'.json'))
def parse(data):
    if not __debug__:
        raise RuntimeError("Format checks require Python without -O")
    h=struct.unpack_from('<32I',data)
    assert h[0]==1 and h[15]==h[16]==h[17]==h[18]==h[26]==h[28]==h[31]==0, 'Unsupported scene layout'
    specs=[('header',1,128),('countries',h[6],300),('province',h[22],2),('territory',h[22],1),('buildings',h[7],32),('armies',h[8],48),('actions',h[9],16),('events',h[10],44),('weather',h[11],16),('capitals',h[19],4)]
    sections={};off=0
    for name,count,size in specs:
        sections[name]={'offset':off,'count':count,'stride':size};off+=count*size
    assert off==len(data),(off,len(data))
    assert h[4]*h[5]==h[22]
    return h,sections

def main():
    parser = argparse.ArgumentParser(description="Audit v1 scene-31 general-ID conflicts and generate an isolated remap candidate.")
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/scene31")
    args = parser.parse_args()
    with zipfile.ZipFile(args.base) as base, zipfile.ZipFile(args.source) as src:
        raw=src.read('assets/stage/conquest31.btl');h,sections=parse(raw)
        sa=sections['armies']; army=[struct.unpack_from('<24H',raw,sa['offset']+i*48) for i in range(sa['count'])]
        refs={r[8] for r in army}-{0}
        bg={r['Id']:r for r in rows(base,'GeneralSettings')};sg={r['Id']:r for r in rows(src,'GeneralSettings')}
        conflicts=sorted(i for i in refs&bg.keys()&sg.keys() if any(sg[i][k]!=bg[i].get(k) for k in sg[i]))
        used=set(bg)|set(sg);remap={};next_id=40000
        for old in conflicts:
            while next_id in used: next_id+=1
            assert next_id<65536
            remap[old]=next_id;used.add(next_id)
        candidate=bytearray(raw)
        for i,r in enumerate(army):
            if r[8] in remap:struct.pack_into('<H',candidate,sa['offset']+i*48+16,remap[r[8]])
        # Verify only declared general fields changed; all coordinates/types/events intact.
        allowed={sa['offset']+i*48+16+j for i,r in enumerate(army) if r[8] in remap for j in (0,1)}
        assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,candidate)))
        added=[]
        for old in sorted(refs & sg.keys()):
            if old not in bg or old in remap:
                r=dict(sg[old]);r['Id']=remap.get(old,old)
                # Scene-only imports: never insert into collection/shop.
                r['InShop']=0
                added.append(r)
        report={'sections':sections,'general_remap':remap,'missing_source_generals':sorted(refs-sg.keys()),'added_general_count':len(added),'army_coordinate_outliers':[i for i,r in enumerate(army) if r[0]>=h[22]],'status':'candidate only; event references, skill semantics, army selection, text and terrain unresolved'}
        out=args.output;out.mkdir(parents=True,exist_ok=True)
        (out/'conquest31.general-remap.btl').write_bytes(candidate)
        (out/'GeneralSettings.append.json').write_text(json.dumps(added,ensure_ascii=False,indent=2))
        (out/'scene31.audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
