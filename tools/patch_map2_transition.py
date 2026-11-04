"""Minimal target-engine map transition fix; never imports source engine.

Original 0x231fec only initializes terrain when current map id == 0.
The scene ID and resource lookups remain unchanged. New branch also initializes
when switching to/from map 2; all other map pairs follow the original path.
This patch alone is not a release: acceleration/runtime QA remains required.
"""
import argparse,json
from pathlib import Path
import struct,hashlib,io
from elftools.elf.elffile import ELFFile
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM

def branch(pc,target):
 delta=target-pc;assert delta%4==0 and -(1<<27)<=delta<(1<<27)
 return 0x14000000|((delta//4)&0x3ffffff)
def beq(pc,target):
 delta=target-pc;assert delta%4==0 and -(1<<20)<=delta<(1<<20)
 return 0x54000000|(((delta//4)&0x7ffff)<<5)
def cbz8(pc,target):
 delta=target-pc;assert delta%4==0 and -(1<<20)<=delta<(1<<20)
 return 0x34000008|(((delta//4)&0x7ffff)<<5)
def patch(raw):
 if not __debug__:
  raise RuntimeError("Patch checks require Python without -O")
 if len(raw)<0x826d10:
  raise ValueError("Input is too short for the version-specific protected ranges")
 elf=ELFFile(io.BytesIO(raw))
 if elf.elfclass!=64 or not elf.little_endian or elf['e_machine']!='EM_AARCH64':
  raise ValueError("This patch only supports the researched little-endian ARM64 ELF layout")
 entry=0x231fec;dest=0x232014;reuse=0x231ff0
 assert struct.unpack_from('<I',raw,entry)[0]==cbz8(entry,dest)
 loads=[(i,p) for i,p in enumerate(elf.iter_segments()) if p['p_type']=='PT_LOAD'];index,seg=loads[0]
 assert seg['p_offset']==0 and seg['p_vaddr']==0 and seg['p_flags']==5
 cave=(seg['p_filesz']+15)&~15;end=cave+36
 assert end<loads[1][1]['p_offset'] and raw[seg['p_filesz']:end]==bytes(end-seg['p_filesz'])
 words=[cbz8(cave,cave+32),0x6b01011f,beq(cave+8,cave+28),0x7100083f,beq(cave+16,cave+32),0x7100091f,beq(cave+24,cave+32),branch(cave+28,reuse),branch(cave+32,dest)]
 result=bytearray(raw);struct.pack_into('<9I',result,cave,*words);struct.pack_into('<I',result,entry,branch(entry,cave))
 ph=elf['e_phoff']+index*elf['e_phentsize'];struct.pack_into('<QQ',result,ph+32,end,end)
 # These are the complete allowed changes, including ELF segment lengths.
 allowed=set(range(entry,entry+4))|set(range(cave,end))|set(range(ph+32,ph+48))
 assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,result)))
 # The speed read/update code and multiplier table remain byte-identical.
 protected=[(0x2671bc,0x2676e0),(0x267c8c,0x267ce0),(0x2b2c00,0x2b2cd0),(0x331000,0x332100),(0x826cd8,0x826d10)]
 assert all(raw[a:b]==result[a:b] for a,b in protected)
 cs=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
 audit={'before_sha256':hashlib.sha256(raw).hexdigest(),'after_sha256':hashlib.sha256(result).hexdigest(),'branch_address':hex(entry),'stub_address':hex(cave),'stub_disassembly':[f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in cs.disasm(bytes(result[cave:end]),cave)],'allowed_ranges':[[hex(entry),hex(entry+4)],[hex(cave),hex(end)],[hex(ph+32),hex(ph+48)]],'protected_speed_ranges':[[hex(a),hex(b)] for a,b in protected],'runtime_verified':False}
 return bytes(result),audit


def main():
 parser=argparse.ArgumentParser(description="Experimental, version-specific ARM64 map-2 transition patch; not an APK builder.")
 parser.add_argument("source",type=Path,help="Self-supplied unmodified matching ELF library")
 parser.add_argument("output",type=Path,help="New library output; must not already exist")
 args=parser.parse_args()
 report_path=args.output.with_name(args.output.name+".audit.json")
 if args.source.resolve()==args.output.resolve() or args.output.exists() or report_path.exists():
  parser.error("Output/report must be new paths, separate from the source library")
 result,audit=patch(args.source.read_bytes())
 args.output.parent.mkdir(parents=True,exist_ok=True)
 with args.output.open("xb") as stream:stream.write(result)
 with report_path.open("x",encoding="utf-8") as stream:
  json.dump(audit,stream,ensure_ascii=False,indent=2);stream.write("\n")
 print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=="__main__":
 main()
