# Copyright 2014 Symantec.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import re
import collections
import csv
import sys


class PingStats(object):
    def __init__(self, test):
        self.test = test
        self.num_vms = 0
        self.num_flows = 0
        self.ping_re = re.compile(r'^\d+ bytes .+ time=([\d.]+) ms$')
        self.info_re = re.compile(r'^(\d+) packets transmitted, '
                                  r'(\d+) received.+$')
        self.stats_re = re.compile(r'^rtt min/avg/max/mdev = ([\d.]+)/'
                                   r'([\d.]+)/([\d.]+)/[\d.]+ ms$')

        self.num_sent = 0.0
        self.num_recv = 0.0
        self.ping_min = float('Inf')
        self.ping_max = 0.0
        self.ping_sum = 0.0
        self.first_ping_sum = 0.0
        self.pings_to_establish_sum = 0.0
        self.count = 0

    def update_min(self, name, value):
        assert 'min' in name
        setattr(self, name, min(getattr(self, name), value))

    def update_max(self, name, value):
        assert 'max' in name
        setattr(self, name, max(getattr(self, name), value))

    def append(self, data):
        self.num_vms += 1

        for result in data['results']:
            self.num_flows += 1

            pings = []
            output = result['output']
            for line in output.splitlines():
                match = self.info_re.match(line)
                if match:
                    num_sent, num_recv = map(float, match.groups())
                    self.num_sent += num_sent
                    self.num_recv += num_recv
                    continue

                match = self.stats_re.match(line)
                if match:
                    min_time, avg_time, max_time = map(float, match.groups())
                    self.update_min('ping_min', min_time)
                    self.update_max('ping_max', max_time)
                    continue

                match = self.ping_re.match(line)
                if match:
                    ping_time = float(match.group(1))
                    pings.append(ping_time)
                    self.ping_sum += ping_time
                else:
                    print line

            if pings:
                self.first_ping_sum += pings[0]
                for i, p in enumerate(pings, 1):
                    if p < avg_time * 1.5:
                        self.pings_to_establish_sum += i
                        break
                self.count += self.test.args.get('ping_count', 10)
            else:
                print 'No ping to <TDOD: address>'

    def output(self , output_file):
        test = self.test
        args = test.args

        result = collections.OrderedDict([
            ('Test Name', test.name),
            ('Number of Pings', args.get('ping_count', 10)),
            #('Number of Tenants', tenants),
            #('Number of Networks', networks),
            ('Number of VMs', self.num_vms),
            #('Time', time),
            ('num_sent', self.num_sent),
            ('num_recv', self.num_recv),
            ('Ping MIN', self.ping_min),
            ('Ping MAX', self.ping_max),
            ('Ping AVG', self.ping_sum / self.count),
            ('First ping AVG', self.first_ping_sum / self.num_flows),
            ('Avg # of pings to establish flow',
             self.pings_to_establish_sum / self.num_flows),
            ('count', self.count),
        ])
       if not output_file:
            fp = sys.stdout
        else:
            fp = open(output_file, 'a')
        writer = csv.writer(fp)
        writer.writerow(result.keys())
        writer.writerow(result.values())
