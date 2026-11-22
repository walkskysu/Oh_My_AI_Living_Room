#!/bin/bash
# See-through output -> cleaned PSDs with Melody's moving parts cut onto their own layers.
# WHITE_INSIDE: the white notebook page / socks are recoloured from the painting too.
# Canvas px (See-through 1024 canvas). Run after run_st.sh; writes /mnt/e/rig_projects/melody/<pose>/<pose>.psd
set -e
cd "$(dirname "$0")"
P=~/.venvs/omalr/bin/python; T=../tools; R=/mnt/e/rig_projects/melody
LEG="560,500 600,470 625,500 660,580 700,660 730,710 780,800 790,870 700,875 650,840 630,790 612,720 590,660 565,600 548,555"
for p in reading bored working done; do
  if [ $p = reading ]; then $P $T/build_psd.py omalr_melody_reading src/omalr_melody_alpha.png alpha $R/reading reading > /dev/null
  else WHITE_INSIDE=1 $P $T/build_psd.py omalr_melody_$p src/omalr_melody_$p.png white $R/$p $p > /dev/null; fi
  # the crossed (top) leg's shin + sock taps on its own bone; it tucks under the thigh at the knee
  PAD=6 $P $T/split_layer.py $R/$p/$p.psd skirt,feet shin_l below $LEG
done
# bored: the arm stretched above her head
$P $T/split_layer.py $R/bored/bored.psd arm_r hand_r below 245,15 345,15 420,80 470,180 510,290 520,345 470,350 440,300 436,215 420,200 380,200 340,140 305,90 245,80
# working: the hand writing with the pencil (+ the pencil's end, which See-through put in the hoodie layer)
KEEP=skin PAD=8 $P $T/split_layer.py $R/working/working.psd arm_r hand_r below 408,340 428,340 470,368 505,398 505,420 492,432 470,445 450,458 425,462 415,448 420,420 430,395 410,358
KEEP=skin $P $T/split_layer.py $R/working/working.psd torso hand_r below 404,336 432,336 440,352 432,368 410,366
# done: the waving hand, cut at the cuff and tucked under the sleeve
PAD=10 $P $T/split_layer.py $R/done/done.psd arm_r hand_r below 200,222 322,222 322,300 306,318 292,342 262,346 250,326 238,300 198,292
