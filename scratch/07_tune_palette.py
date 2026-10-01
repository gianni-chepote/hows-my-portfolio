"""Step 7: snap the Dominion factsheet hues into a legible OKLCH band on white."""
import math, sys

def srgb_to_lin(c): return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def lin_to_srgb(c): return 12.92*c if c <= 0.0031308 else 1.055*c**(1/2.4)-0.055
def hex_to_oklch(h):
    r,g,b=[srgb_to_lin(int(h[i:i+2],16)/255) for i in (1,3,5)]
    l=0.4122214708*r+0.5363325363*g+0.0514459929*b; m=0.2119034982*r+0.6806995451*g+0.1073969566*b; s=0.0883024619*r+0.2817188376*g+0.6299787005*b
    l,m,s=[x**(1/3) for x in (l,m,s)]
    L=0.2104542553*l+0.7936177850*m-0.0040720468*s; A=1.9779984951*l-2.4285922050*m+0.4505937099*s; B=0.0259040371*l+0.7827717662*m-0.8086757660*s
    return L, math.hypot(A,B), math.degrees(math.atan2(B,A))%360
def oklch_to_hex(L,C,H):
    A=C*math.cos(math.radians(H)); B=C*math.sin(math.radians(H))
    l=(L+0.3963377774*A+0.2158037573*B)**3; m=(L-0.1055613458*A-0.0638541728*B)**3; s=(L-0.0894841775*A-1.2914855480*B)**3
    rgb=[4.0767416621*l-3.3077115913*m+0.2309699292*s, -1.2684380046*l+2.6097574011*m-0.3413193965*s, -0.0041960863*l-0.7034186147*m+1.7076147010*s]
    if any(x<-1e-4 or x>1+1e-4 for x in rgb): return None
    return '#'+''.join(f'{round(max(0,min(1,lin_to_srgb(x)))*255):02X}' for x in rgb)
def fit(h, L, Cmin=0.11):
    _,C,H=hex_to_oklch(h); C=max(C,Cmin)
    while C>0 and oklch_to_hex(L,C,H) is None: C-=0.005
    return oklch_to_hex(L,C,H)

ref = dict(violet="#5A54FF", green="#8ED976", yellow="#FFF67A", amber="#FED072", peach="#F39D73",
           coral="#EE7170", pink="#EB77AA", lavender="#9C8BC2", navy="#2A496B", teal="#408175")
targets = dict(violet=None, green=0.66, yellow=0.74, amber=0.72, peach=0.68, coral=0.62, pink=0.60,
               lavender=0.58, navy=0.46, teal=0.56)
for k,h in ref.items():
    L,C,H=hex_to_oklch(h)
    out=h if targets[k] is None else fit(h,targets[k])
    print(f"{k:9s} {h} L={L:.2f} C={C:.3f} H={H:5.1f} -> {out}")
