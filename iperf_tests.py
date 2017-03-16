#!/usr/bin/env python

################################
# Jimmy Cullen                 #
# Version 1.0, 2011-05-10      #
# The University of Manchester #
################################

# Python script to graph iperf test results from the bash script found at:
# http://www.jb.man.ac.uk/~jcullen/code/bash/iperf_tests.sh

# Data recorded in the output of the script on the client machine is int the
# form of four rows per test:
# line 1 - iperf command line run on client
# line 2 - summary of the test
# line 3 - csv output for the forward direction test
# line 4 - csv output for the reverse direction test

# csv output is as follows:

# date and time, server IP, server port, client IP, client port, iperf process number, time interval, amount of data transferred (bytes), bandwidth (bits per second), jitter (milliseconds), number of lost datagrams, total number of datagrams sent, percentage loss, number of datagrams received out of order

# e.g.

# 20110503113013,192.168.10.206,5001,192.168.10.100,32971,3,0.0-10.0,627420932,501941865,0.002,1,69932,0.001,0

import sys
import numpy as np
import pylab
import re


colours = ['b','g','r','c','m','y','k']
symbols = ['-', '--', '-.', ':', '.', ',', 'o', 'v', '^', '<', '>', '1', '2', '3', '4', 's', 'p', '*', 'h', 'H', '+', 'x', 'D', 'd', '|', '_']


pkt_size_arr = [1000, 1472, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 8972]
bandwidth = []
for a in xrange(100, 10100, 100):
  bandwidth.append(a)

cmd_line = []
client_data = []
forward_data = []
reverse_data = []

# get filename
if len(sys.argv) < 2:
  print "Too few command line arguments!"
else:
  input_file = sys.argv[1]

common_root = input_file[18:-4]

# read in iperf data into a variable called data
f = open(input_file, 'r')
data = f.readlines()
f.close()

for line in data:
  if re.search(r'^/', line):
    # place copy in cmd_line array
    cmd_line.append(line.rstrip())
  
    # sanity checks:
    # - make sure the next line exists (NB len is +1 the index position)
    # - make sure the next lines begin with numbers
    if len(data)-1 >= data.index(line)+1 and re.search(r'^[0-9]', data[data.index(line)+1]):
      # add the next line to client_data array
      client_data.append(data[data.index(line) + 1].rstrip())
   
    if len(data)-1 >= data.index(line)+2 and re.search(r'^[0-9]', data[data.index(line)+2]):
      # add the next line to forward_data array
      forward_data.append(data[data.index(line) + 2].rstrip())

    if len(data)-1 >= data.index(line)+3 and re.search(r'^[0-9]', data[data.index(line)+3]):
      # add the next line to reverse_data array
      reverse_data.append(data[data.index(line) + 3].rstrip())


# define some lists
cmd_line_bandwidth = []
cmd_line_pkt_size = []

client_data_data_transferred = []
client_data_bandwidth = []

forward_data_data_transferred = []
forward_data_bandwidth = []
forward_data_jitter = []
forward_data_lost_datagrams = []
forward_data_total_datagrams = []
forward_data_packets_out_of_order = []

reverse_data_data_transferred = []
reverse_data_bandwidth = []
reverse_data_jitter = []
reverse_data_lost_datagrams = []
reverse_data_total_datagrams = []
reverse_data_packets_out_of_order = []

# cmd_line
for k in range(len(cmd_line)):
  cmd_line_bandwidth.append(int(cmd_line[k].split()[5][:-1]))
  cmd_line_pkt_size.append(int(cmd_line[k].split()[9][:-1]))

# client_data
for l in range(len(client_data)):
  client_data_bandwidth.append(int(client_data[l].split(',')[7])/1000000)
  client_data_data_transferred.append(int(client_data[l].split(',')[8])/1000000)

# forward_data
for m in range(len(forward_data)):
  forward_data_data_transferred.append(int(forward_data[m].split(',')[7])/1000000)
  forward_data_bandwidth.append(int(forward_data[m].split(',')[8])/1000000)
  forward_data_jitter.append(forward_data[m].split(',')[9])
  forward_data_lost_datagrams.append(int(forward_data[m].split(',')[10]))
  forward_data_total_datagrams.append(int(forward_data[m].split(',')[11]))
  forward_data_packets_out_of_order.append(int(forward_data[m].split(',')[13]))

# reverse_data
for m in range(len(reverse_data)):
  reverse_data_data_transferred.append(int(reverse_data[m].split(',')[7])/1000000)
  reverse_data_bandwidth.append(int(reverse_data[m].split(',')[8])/1000000)
  reverse_data_jitter.append(reverse_data[m].split(',')[9])
  reverse_data_lost_datagrams.append(int(reverse_data[m].split(',')[10]))
  reverse_data_total_datagrams.append(int(reverse_data[m].split(',')[11]))
  reverse_data_packets_out_of_order.append(int(reverse_data[m].split(',')[13]))

# Make some plots

################################################################
###  1a Requested bandwidth vs. achieved bandwidth (forward)
################################################################

pylab.figure()
col = 0
sym = 0

for qf in pkt_size_arr:
  temp1f = []
  temp2f = []
  for pf in range(len(cmd_line_pkt_size)):
    if qf == cmd_line_pkt_size[pf]:
      temp1f.append(cmd_line_bandwidth[pf])
      temp2f.append(forward_data_bandwidth[pf])
  
  pylab.plot(temp1f, temp2f, colours[col]+symbols[sym], label = repr(qf))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Achieved Bandwidth (Mbps)')
  pylab.title('Requested versus achieved UDP bandwidth\nfor varying datagram sizes (forward)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

# add legend
pylab.legend(loc='best')
pylab.savefig('req_bw_vs_ach_bw_forward_' + common_root)

################################################################
###  1b Requested bandwidth vs. achieved bandwidth (reverse)
################################################################

pylab.figure()
col = 0
sym = 0

for qr in pkt_size_arr:
  temp1r = []
  temp2r = []
  for pr in range(len(cmd_line_pkt_size)):
    if qr == cmd_line_pkt_size[pr]:
      temp1r.append(cmd_line_bandwidth[pr])
      temp2r.append(reverse_data_bandwidth[pr])

  pylab.plot(temp1r, temp2r, colours[col]+symbols[sym], label = repr(qr))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Achieved Bandwidth (Mbps)')
  pylab.title('Requested versus achieved UDP bandwidth\nfor varying datagram sizes (reverse)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

# add legend
pylab.legend(loc='best')
pylab.savefig('req_bw_vs_ach_bw_reverse_' + common_root)

################################################################
###  2a Requested bandwidth vs. jitter (forward)
################################################################

pylab.figure()
col = 0
sym = 0

for qqf in pkt_size_arr:
  temp3f = []
  temp4f = []
  for ppf in range(len(cmd_line_pkt_size)):
    if qqf == cmd_line_pkt_size[ppf]:
      temp3f.append(cmd_line_bandwidth[ppf])
      temp4f.append(forward_data_jitter[ppf])

  pylab.plot(temp3f, temp4f, colours[col]+symbols[sym], label = repr(qqf))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Jitter (microseconds)')
  pylab.title('Requested UDP bandwidth versus jitter\nfor varying datagram sizes (forward)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

# add legend
pylab.legend(loc='best')
pylab.savefig('req_bw_vs_jitter_forward_' + common_root)
################################################################
###  2b Requested bandwidth vs. jitter (reverse)
################################################################

pylab.figure()
col = 0
sym = 0

for qqr in pkt_size_arr:
  temp3r = []
  temp4r = []
  for ppr in range(len(cmd_line_pkt_size)):
    if qqr == cmd_line_pkt_size[ppr]:
      temp3r.append(cmd_line_bandwidth[ppr])
      temp4r.append(reverse_data_jitter[ppr])

  pylab.plot(temp3r, temp4r, colours[col]+symbols[sym], label = repr(qqr))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Jitter (microseconds)')
  pylab.title('Requested UDP bandwidth versus jitter\nfor varying datagram sizes (reverse)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

# add legend
pylab.legend(loc='best')
pylab.savefig('req_bw_vs_jitter_reverse_' + common_root)
################################################################
###  3a Requested bandwidth vs. percentage lost packets (forward)
################################################################

pylab.figure()
col = 0
sym = 0
for qqqf in pkt_size_arr:
  temp5f = []
  temp6f = []
  for pppf in range(len(cmd_line_pkt_size)):
    if qqqf == cmd_line_pkt_size[pppf]:
      temp5f.append(cmd_line_bandwidth[pppf])
      temp6f.append(float(forward_data_lost_datagrams[pppf])/float(forward_data_total_datagrams[pppf])* 100)

  pylab.plot(temp5f, temp6f, colours[col]+symbols[sym], label = repr(qqqf))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Percentage lost packets')
  pylab.title('Requested bandwidth versus percentage packet loss\nfor varying datagram sizes (forward)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

pylab.legend(loc='best')
pylab.savefig('req_bw_vs_pcnt_pkt_loss_forward_' + common_root)
################################################################
###  3b Requested bandwidth vs. percentage lost packets (reverse)
################################################################

pylab.figure()
col = 0
sym = 0
for qqqr in pkt_size_arr:
  temp5r = []
  temp6r = []
  for pppr in range(len(cmd_line_pkt_size)):
    if qqqr == cmd_line_pkt_size[pppr]:
      temp5r.append(cmd_line_bandwidth[pppr])
      temp6r.append(float(reverse_data_lost_datagrams[pppr])/float(reverse_data_total_datagrams[pppr])* 100)

  pylab.plot(temp5r, temp6r, colours[col]+symbols[sym], label = repr(qqqr))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Percentage lost packets')
  pylab.title('Requested bandwidth versus percentage packet loss\nfor varying datagram sizes (reverse)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

pylab.legend(loc='best')
pylab.savefig('req_bw_vs_pcnt_pkt_loss_reverse_' + common_root)

################################################################
###  4a Requested bandwidth vs. out of order packets (forward)
################################################################

pylab.figure()
col = 0
sym = 0
for qqqqf in pkt_size_arr:
  temp7f = []
  temp8f = []
  for ppppf in range(len(cmd_line_pkt_size)):
    if qqqqf == cmd_line_pkt_size[ppppf]:
      temp7f.append(cmd_line_bandwidth[ppppf])
      temp8f.append(forward_data_packets_out_of_order[ppppf])

  pylab.plot(temp7f, temp8f, colours[col]+symbols[sym], label = repr(qqqqf))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Out of order packets')
  pylab.title('Requested bandwidth versus out of order packets\nfor varying datagram sizes (forward)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

pylab.legend(loc='best')
pylab.savefig('req_bw_vs_out_of_order_forward_' + common_root)
################################################################
###  4b Requested bandwidth vs. out of order packets (reverse)
################################################################

pylab.figure()
col = 0
sym = 0
for qqqqr in pkt_size_arr:
  temp7r = []
  temp8r = []
  for ppppr in range(len(cmd_line_pkt_size)):
    if qqqqr == cmd_line_pkt_size[ppppr]:
      temp7r.append(cmd_line_bandwidth[ppppr])
      temp8r.append(forward_data_packets_out_of_order[ppppr])

  pylab.plot(temp7r, temp8r, colours[col]+symbols[sym], label = repr(qqqqr))
  pylab.grid(True)
  pylab.xlabel('Requested Bandwidth (Mbps)')
  pylab.ylabel('Out of order packets')
  pylab.title('Requested bandwidth versus out of order packets\nfor varying datagram sizes (reverse)')

  # increment colour and symbols
  if col < 6:
    col = col+1
  else:
    col = 0
    sym = sym+1

pylab.legend(loc='best')
pylab.savefig('req_bw_vs_out_of_order_reverse_' + common_root)


# display the plots
pylab.show()
