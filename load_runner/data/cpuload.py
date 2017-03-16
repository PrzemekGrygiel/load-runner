import re
import collections
import csv
import sys
import json
from operator import sub
from operator import add

class CPUStats(object):
    def __init__(self):
         print "Start CPU stats ..."
         self.cpu_sum = {}
         self.cpu_all = {}
        
    def append(self, data):
        for result in data['results']:
            output = result['output']
        json_result = json.loads(output)
       
        for i in json_result:
            try:
                self.cpu_all.update({i.items()[0][0]:[]})
            except IndexError, e:
                continue
        for i in json_result:
            try:
                 for k,v in i.iteritems():
		     self.cpu_all[k].append(v)
            except:
                continue

    def output(self, output_file=None):
        print "CPU number, total, user, nice, system, idle, iowait, irq, softirq, streal" 
        for key, value in self.cpu_all.iteritems():
            diff2 = [0,0,0,0,0,0,0,0]
            for a, b in enumerate(value):
                try:
                    diff = map(sub, value[a+1], value[a])
                    diff2 =  map(add, diff, diff2)
                    #print diff2
                    # Uncoment if samples are needed
                    #total = diff[0]*100/sum(diff) + diff[1]*100/sum(diff) + diff[2]*100/sum(diff) + diff[4]*100/sum(diff) + diff[5]*100/sum(diff) + diff[6]*100/sum(diff) + diff[7]*100/sum(diff)
                    #if key == 'cpu':
                    #    print "all_cpu, {}, {}, {}, {}, {}, {}, {}, {}, {}" .format(total, diff[0]*100/sum(diff), diff[1]*100/sum(diff),diff[2]*100/sum(diff), diff[3]*100/sum(diff), diff[4]*100/sum(diff), diff[5]*100/sum(diff), diff[6]*100/sum(diff), diff[7]*100/sum(diff))
                    #else: 
                    #     print "{}, {}, {}, {}, {}, {}, {}, {}, {}, {}" .format(key,total, diff[0]*100/sum(diff), diff[1]*100/sum(diff),diff[2]*100/sum(diff), diff[3]*100/sum(diff), diff[4]*100/sum(diff), diff[5]*100/sum(diff), diff[6]*100/sum(diff), diff[7]*100/sum(diff))
                except IndexError:
                    continue
            total = diff2[0]*100/sum(diff2) + diff2[1]*100/sum(diff2) + diff2[2]*100/sum(diff2) + diff2[4]*100/sum(diff2) + diff2[5]*100/sum(diff2) + diff2[6]*100/sum(diff2) + diff2[7]*100/sum(diff2)
            if key == 'cpu':
                print "all_cpu, {}, {}, {}, {}, {}, {}, {}, {}, {}" .format(total, diff2[0]*100/sum(diff2), diff2[1]*100/sum(diff2),diff2[2]*100/sum(diff2), diff2[3]*100/sum(diff2), diff2[4]*100/sum(diff2), diff2[5]*100/sum(diff2), diff2[6]*100/sum(diff2), diff2[7]*100/sum(diff2))
            else:
                print "{}, {}, {}, {}, {}, {}, {}, {}, {}, {}" .format(key, total, diff2[0]*100/sum(diff2), diff2[1]*100/sum(diff2),diff2[2]*100/sum(diff2), diff2[3]*100/sum(diff2), diff2[4]*100/sum(diff2), diff2[5]*100/sum(diff2), diff2[6]*100/sum(diff2), diff2[7]*100/sum(diff2))

        if not output_file:
            fp = sys.stdout           
        else:
            fp = open(output_file, 'a')
            writer = csv.writer(fp)
            writer.writerow(result.keys())
            writer.writerow(result.values())
            fp.close()
