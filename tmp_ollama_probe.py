from urllib.request import Request, urlopen
import re

headers = {"User-Agent": "Summit-Transcriber/1.0"}

for url in (
    "https://ollama.com/library/llama3.2",
    "https://ollama.com/library/llama3.2/tags",
    "https://ollama.com/library/qwen2.5",
):
    req = Request(url, headers=headers)
    with urlopen(req, timeout=20) as response:
        data = response.read().decode("utf-8", "replace")
    print("====", url, "len", len(data))
    sizes = re.findall(r"[\d.]+\s*(?:GB|MB|GiB|MiB)", data, re.I)
    print("sizes sample", sizes[:20])
    # look around first GB
    idx = re.search(r"[\d.]+\s*GB", data, re.I)
    if idx:
        print(data[max(0, idx.start() - 120) : idx.end() + 80].replace("\n", " ")[:400])
    print()
