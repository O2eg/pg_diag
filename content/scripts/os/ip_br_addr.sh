#!/bin/bash

ip -br addr 2>/dev/null || true
printf '\n/etc/hosts\n'
cat /etc/hosts
