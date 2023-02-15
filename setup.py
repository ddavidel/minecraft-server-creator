import os
os.system("if EXIST config.ini call ServerCreator.py")
os.system("pip install wget")
os.system("echo configured>config.ini")
import wget
url = ""
wget.download(url)

os.system("call ServerCreator.py")