#!/bin/sh

LC_ALL=C ps ax -o pid,ppid,user,stat,etime,pcpu,pmem,comm,args | awk '
NR == 1 {
    print
    next
}

$8 == "postgres" || $8 == "postmaster" {
    print
    found = 1
}

END {
    if (!found) {
        print "No PostgreSQL server processes found in ps output."
    }
}
'
