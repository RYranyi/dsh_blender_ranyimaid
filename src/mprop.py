"""mprop.py - measured proportions of the chibi maid (total height 1.0 m).

All numbers derived from the 7 reference sheets (front/side/back/top/bottom
orthographic figures) by silhouette + landmark measurement.
"""
import math
from math import sin, cos, pi

H = 1.0

# ---- vertical landmarks (z) -------------------------------------------------
Z_HAIR_TOP      = 0.982
Z_SKULL_TOP     = 0.968
Z_HEADBAND      = 0.878   # centre of the band on the forehead
Z_EYE           = 0.7255
Z_BROW          = 0.772
Z_NOSE          = 0.688
Z_MOUTH         = 0.6485
Z_CHIN          = 0.600
Z_NECK_TOP      = 0.612
Z_NECK_BOT      = 0.566
Z_SHOULDER      = 0.572
Z_ARMHOLE       = 0.508
Z_CHEST         = 0.520
Z_WAIST         = 0.448
Z_WAISTBAND_TOP = 0.459
Z_WAISTBAND_BOT = 0.432
Z_HIP           = 0.395
Z_APRON_HEM     = 0.243
Z_SKIRT_HEM     = 0.204
Z_THIGH_EXPOSED = 0.198
Z_SOCK_TOP      = 0.176
Z_KNEE          = 0.140
Z_ANKLE         = 0.062
Z_SOLE          = 0.000

# ---- horizontal landmarks (x half-widths) -----------------------------------
X_HAIR_MAX      = 0.2315
X_SKULL         = 0.1680
X_FACE_VISIBLE  = 0.1300
X_EYE_C         = 0.1000
EYE_W           = 0.1120
EYE_H           = 0.0880
EYE_TILT_DEG    = 12.5
X_NECK          = 0.0370
X_SHOULDER      = 0.1090
X_PUFF_MAX      = 0.1745
X_BODICE        = 0.0955
X_WAIST         = 0.0900
X_APRON_BIB     = 0.0660
X_SKIRT_HEM     = 0.1915
X_LEG_IN        = 0.0165
X_LEG_OUT       = 0.0785
X_SOCK_IN       = 0.0205
X_SOCK_OUT      = 0.0735
X_SHOE_IN       = 0.0075
X_SHOE_OUT      = 0.0855

# ---- depth landmarks (y; -Y is front) ---------------------------------------
Y_HEAD_C        = 0.0040
Y_FACE          = -0.1520   # skull front at mid face
Y_NOSE          = -0.1620
Y_FRINGE        = -0.2070
Y_HAIR_BACK     =  0.2210
Y_EAR           =  0.0450
Y_NECK          = -0.0040
Y_CHEST_F       = -0.0800
Y_CHEST_B       =  0.0700
Y_WAIST_F       = -0.0760
Y_WAIST_B       =  0.0710
Y_HIP_F         = -0.0870
Y_HIP_B         =  0.0840
Y_SKIRT_F       = -0.1370
Y_SKIRT_B       =  0.1400
Y_LEG_F         = -0.0540
Y_LEG_B         =  0.0540
Y_TOE           = -0.1050
Y_HEEL          =  0.0530

# ---- palette (sRGB hex, converted to linear by mcore.hexc) ------------------
C_SKIN          = "#F7CBB8"
C_SKIN_SHADE    = "#E2A99A"
C_BLUSH         = "#EE948C"
C_HAIR_DARK     = "#4A2E1E"
C_HAIR_MID      = "#654028"
C_HAIR_LIGHT    = "#7C5539"
C_NAVY          = "#2B3350"
C_NAVY_DARK     = "#1F2740"
C_WHITE         = "#F4F1F0"
C_WHITE_SHADE   = "#DCD6DA"
C_SHOE          = "#6B3B22"
C_SHOE_DARK     = "#43210F"
C_IRIS_DARK     = "#1D4C6B"
C_IRIS_MID      = "#2E7EA8"
C_IRIS_LIGHT    = "#7FC6E3"
C_IRIS_PALE     = "#BFE7F4"
C_PUPIL         = "#102A3C"
C_RED           = "#C3251A"
C_MOUTH         = "#A34B46"
C_LASH          = "#1A1412"
C_EYEBROW       = "#6B4630"
