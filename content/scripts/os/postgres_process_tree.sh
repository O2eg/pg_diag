#!/bin/bash

ps fax -o pid,ppid,user,stat,etime,pcpu,pmem,args | awk '
NR == 1 {
    print
    next
}

/(^|[[:space:]\/])postgres(:|[[:space:]]|$)/ ||
/(^|[[:space:]\/])postmaster(:|[[:space:]]|$)/ {
    print
    found = 1
}

END {
    if (!found) {
        print "No PostgreSQL server processes found in ps fax output."
    }
}
'
