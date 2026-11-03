import re
import urllib.request

for u in [
    "https://codh.rois.ac.jp/historical-gis/edo-road/",
    "https://codh.rois.ac.jp/historical-gis/edo-post/",
    "https://geoshape.ex.nii.ac.jp/edo/road/",
]:
    html = urllib.request.urlopen(u, timeout=30).read().decode("utf-8", "replace")
    links = re.findall(r'href="([^"]+)"', html)
    print("===", u)
    for L in links:
        low = L.lower()
        if any(x in low for x in [".zip", ".gpkg", ".geojson", ".json", "download", "edo"]):
            print(" ", L)
