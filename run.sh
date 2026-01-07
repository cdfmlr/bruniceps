#!/bin/bash

nohup ./venv/bin/python bruniceps.py -c config sync &
tail -f nohup.out
