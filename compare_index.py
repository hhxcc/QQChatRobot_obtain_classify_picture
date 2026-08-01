import json, pathlib
root=pathlib.Path(r"output/泰拉大典")
idx=json.load(open(root/"index.json",encoding="utf-8"))
index_files=[p['file_name'] for p in idx['pages']]
fs=[str(p.relative_to(root)).replace("\\","/") for p in root.rglob("*") if p.is_file()]
missing=[name for name in index_files if not any(f.endswith(name) for f in fs)]
extra=[f for f in fs if f!="index.json" and not any(f.endswith(name) for name in index_files)]
print("total_index=",len(index_files))
print("total_fs=",len(fs))
print("missing_count=",len(missing))
for m in missing[:200]: print("MISSING:",m)
print("extra_count=",len(extra))
for e in extra[:200]: print("EXTRA:",e)
