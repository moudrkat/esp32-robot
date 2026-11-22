"""Simple Czech without diacritics for pretraining: Tatoeba sentences + a slice of OpenSubtitles, kept only when
every word is among the most common ones (a small world, as in TinyStories)."""
import bz2, collections, gzip, re, sys, unicodedata, zlib
def plain(s):
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))
ok = re.compile(r"[a-z0-9 ,.!?'-]+")
def clean(s):
    s = plain(s.strip()).lower()
    s = re.sub(r"^[-– ]+", "", s).replace("…", "...").replace("„", "").replace("“", "").replace('"', "")
    s = re.sub(r"\s+", " ", s).strip()
    return s if 6 <= len(s) <= 90 and ok.fullmatch(s) and re.search(r"[a-z]{2}", s) else None
lines = []
for l in bz2.open("data/ces_sentences.tsv.bz2", "rt", encoding="utf8"):
    c = clean(l.rstrip("\n").split("\t")[2])
    if c: lines.append(c)
nt = len(lines)
d = zlib.decompressobj(31); buf = b""
with open("data/cs-subs.part.gz", "rb") as f:
    while True:
        chunk = f.read(1 << 20)
        if not chunk: break
        try: buf += d.decompress(chunk)
        except zlib.error: break
        *full, buf = buf.split(b"\n")
        for b in full:
            c = clean(b.decode("utf8", "ignore"))
            if c: lines.append(c)
lines = list(dict.fromkeys(lines))
cnt = collections.Counter(w for l in lines for w in re.findall(r"[a-z]+", l))
top = {w for w, _ in cnt.most_common(int(sys.argv[1]))}
keep = [l for l in lines if all(w in top for w in re.findall(r"[a-z]+", l))]
open("data/cs-corpus.txt", "w").write("\n".join(keep) + "\n")
print(f"tatoeba {nt}, all unique {len(lines)}, kept {len(keep)} with top {sys.argv[1]} words, {sum(len(l) for l in keep)/1e6:.0f} MB, words {sum(len(l.split()) for l in keep)/1e6:.1f}M")
