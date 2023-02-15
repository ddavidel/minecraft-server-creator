import os
os.system("if EXIST config.ini call main.exe")
os.system("pip install wget")
os.system("echo configured>config.ini")
import wget
url = "https://github.com/ddavidel/minecraft-server-creator/releases/download/Releases/ServerCreator.exe"
wget.download(url)

os.system("call main.exe")