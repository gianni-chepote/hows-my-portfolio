"""Step 7b: Dominion hues fitted for the dark panel (#12112B)."""
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("t", pathlib.Path(__file__).with_name("07_tune_palette.py"))
src = pathlib.Path(__file__).with_name("07_tune_palette.py").read_text().split("ref = dict")[0]
ns = {}; exec(src, ns)
ref = dict(violet="#5A54FF", green="#8ED976", yellow="#FFF67A", amber="#FED072", peach="#F39D73",
           coral="#EE7170", pink="#EB77AA", lavender="#9C8BC2", navy="#2A496B", teal="#408175", sky="#3F8FC9")
L = dict(violet=0.62, green=0.74, yellow=0.84, amber=0.78, peach=0.72, coral=0.66, pink=0.68,
         lavender=0.66, navy=0.60, teal=0.64, sky=0.70)
for k, h in ref.items():
    print(k, ns["fit"](h, L[k], Cmin=0.12))
# violet ramp for the heatmap: brand hue 276.6, from dark-neutral to bright
_, _, H = ns["hex_to_oklch"]("#5A54FF")
print("violet ramp", [ns["fit"]("#5A54FF", l, Cmin=c) for l, c in ((0.36, 0.06), (0.46, 0.13), (0.56, 0.2), (0.68, 0.17), (0.80, 0.1))])
print("coral ramp", [ns["fit"]("#EE7170", l, Cmin=c) for l, c in ((0.40, 0.06), (0.52, 0.12), (0.66, 0.15))])
