#!/usr/bin/python
"""
*********************************************************
    Application : housekeeper.py
    Written By:     Colin Leek
    Purpose: File Management script to perform automatic actions defined by rules
    Version: 0.10

    Description: 
*********************************************************
"""
# Import Modules
import datetime as dt
import os
import sys
import getopt
import re
import shutil
import glob

# Authorship information
__author__ = "Colin Leek"
__copyright__ = ""
__credits__ = ""
__license__ = "GPL"
__version__ = "0.10"
__maintainer__ = ""
__email__ = ""
__status__ = "Prototype"
#__status__ = "Prototype/Development/Production"

class RuleValue:
    "This is Rule Value Class"
    def __init__(self, o="", sp="", sf="", fa=0, tp="", tf=""):
        self.operation = o
        self.sourcepath = sp
        self.sourcefile = sf
        self.fileage = (float(fa)*24*60*60*60)
        self.targetpath = tp
        self.targetfile = tf

def logwrite(unit, message, status="INFO" ):
    linedate = dt.datetime.now()
    status = status+" "
    unit = unit+"        "
    logline =str(linedate)+" ["+status[:5]+"] - "+unit[:8]+" - "+message+"\n"
    lf.write(logline)
    print(logline)

def copy_function(aline):
    temp = aline.split("|")
    action = RuleValue(temp[0], temp[1], temp[2], temp[3], temp[4], temp[5])
    if not os.path.exists(action.sourcepath):
        logwrite("COPY", "The source path does not exists "+action.sourcepath, "ERROR")
        return
    if not os.path.exists(action.targetpath):
        logwrite("COPY", "The target path does not exists "+action.targetpath, "ERROR")
        return
    if action.fileage == 0:
        # If there is not a file age defined the just copy the files as defined by the rule
        for file in glob.glob(action.sourcepath + "\\" + action.sourcefile):
            # todo shutil.copy(file, action.targetpath+"\\")
            message = "Successfully copied " + file
            logwrite("COPY", message)
    elif action.fileage > 0:
        # There is an age limit on the files to be copied
        current_dt = dt.datetime.now()
        current_ts = current_dt.timestamp()
        for file in glob.glob(action.sourcepath+"\\"+action.sourcefile):
            file_ts = os.stat(file).st_mtime
            if (current_ts - file_ts) > action.fileage:
                # todo shutil.copy(file, action.targetpath+"\\")
                message = "Successfully copied " + file
                logwrite("COPY", message)


def archive_function(aline):
    # todo Need function to Archive(gzip)
    temp = aline.split("|")
    action = RuleValue(temp[0], temp[1], temp[2], temp[3], temp[4], temp[5])
    if not os.path.exists(action.sourcepath):
        logwrite("COPY", "The source path does not exists " + action.sourcepath, "ERROR")
        return
    if not os.path.exists(action.targetpath):
        logwrite("COPY", "The target path does not exists " + action.targetpath, "ERROR")
        return

    logwrite("ARCHIVE", "This is a test Log Message")


def group_archive_function(aline):
    # todo Need function to GroupArchive(gzip)
    print("Archive Group Function")
    temp = aline.split("|")
    action = RuleValue(temp[0], temp[1], temp[2], temp[3], temp[4], temp[5])


def delete_function(aline):
    # todo Need function to Delete
    print("Delete Function")
    temp = aline.split("|")
    action = RuleValue(temp[0], temp[1], temp[2], temp[3], temp[4], temp[5])


def move_function(aline):
    # todo Need function to Move
    print("Move Function")
    temp = aline.split("|")
    action = RuleValue(temp[0], temp[1], temp[2], temp[3], temp[4], temp[5])

#**********************************************
#* Main Script
#**********************************************
argv = sys.argv[1:]
rulesfile = ''
try:
    opts, args = getopt.getopt(argv, "hi:", ["ifile="])
except getopt.GetoptError:
    print("Usage:")
    print('housekeeper.py -i <rulesfile>')
    sys.exit(2)
for opt, arg in opts:
    if opt == '-h':
        print("Usage:")
        print('housekeeper.py -i <rulesfile>')
        sys.exit()
    elif opt in ("-i", "--ifile"):
        rulesfile = arg
        logext = str(dt.date.today()) + ".log"
        logfile = arg.replace('.txt', logext)
f = open(rulesfile, 'r')
lines = f.readlines()
lf = open(logfile, 'a')

logwrite("MAIN", "Starting House keeping.")
for line in lines:
    regexp = re.compile(r'^[CAGDM]*|')
    temp = regexp.search(line)
    action=temp.group()
    if action == '':
        continue
    #select the required action
    if action == "C":
        # Call the Copy Function
        copy_function(line)
    elif action == 'A':
        # Call the Archive Function
        archive_function(line)
    elif action == 'GA':
        # Call the Group Archive function
        delete_function(line)
    elif action == 'D':
        # Call the Delete Function
        delete_function(line)
    elif sction == 'M':
        # Call the Move Function
        move_function(line)
    else:
        continue

print("END of Script")


