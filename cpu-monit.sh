#!/bin/sh
echo "[ "  > /tmp/results.txt; 
for num in $(seq 1 $1)
 do sleep 1 
 grep cpu /proc/stat | awk '{print "{\""$1"\": ["$2","$3","$4","$5","$6","$7","$8","$9"]},"}' >> /tmp/results.txt
done 
echo "{} ]" >> /tmp/results.txt;
