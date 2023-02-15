import os
os.system("color 8f")
os.system("title Creatore Server Minecraft")
os.system("if NOT EXIST config.ini call setup.py")
import wget

def clear():
    os.system("cls")
def pause():
    os.system("pause")

def help(param):
    if(param == "jar"):
        print("Il tipo di JAR e' il software che usera' il server. Spigot ti permette di utlizzare i plugin. Vanilla e' quello predefinito.")

def menu():
    clear()
    print("\tMenu Principale\n")
    print("\t1) Crea un server")
    print("\t2) Controlla aggiornamenti")
    print("\t0) Esci")
    s = int(input("\n\t>>>"))
    return s

def crea():
    clear()
    print("\tScegli il nome del server:\n")
    nome = str(input("\t>>>"))

    clear()
    print("\tScegli il JAR del server:\n")
    print("\t1) Vanilla")
    print("\t2) Spigot")
    jType = int(input("\t>>>"))
    while (jType != 1 and jType != 2):
        jType = int(input("\t>>>"))
    
    clear()
    print("\tScegli la versione del server:\n")
    print("\t1) 1.8.9")
    print("\t2) 1.12.2")
    print("\t3) 1.13.2")
    print("\t4) 1.14.4")
    print("\t5) 1.15.2")
    jVersion = int(input("\t>>>"))
    while (jVersion < 1 or jVersion > 5):
        jVersion = int(input("\t>>>"))
    
    clear()
    print("\tScegli quanta RAM dedicare al server [MB]:\n")
    dRam = int(input("\t>>>"))
    while (dRam < 0):
        print("\tNon puoi inserire un valore minore di 0.")
        dRam = int(input("\t>>>"))
    
    clear()
    print("\t\tREVISIONE:\n")
    print("\tNome server: "+nome)
    if(jType == 1):
        print("\tTipo JAR: Vanilla\n")
    else:
        print("\tTipo JAR: Spigot\n")
    
    if(jType == 1):
        if(jVersion == 1):
            print("\tVersione JAR: 1.8.9\n")
            url = "https://launcher.mojang.com/mc/game/1.8.9/server/b58b2ceb36e01bcd8dbf49c8fb66c55a9f0676cd/server.jar"
        if(jVersion == 2):
            print("\tVersione JAR: 1.12.2\n")
            url = "https://launcher.mojang.com/mc/game/1.12.2/server/886945bfb2b978778c3a0288fd7fab09d315b25f/server.jar"
        if(jVersion == 3):
            print("\tVersione JAR: 1.13.2\n")
            url = "https://launcher.mojang.com/v1/objects/3737db93722a9e39eeada7c27e7aca28b144ffa7/server.jar"
        if(jVersion == 4):
            print("\tVersione JAR: 1.14.4\n")
            url = "https://launcher.mojang.com/v1/objects/d0d0fe2b1dc6ab4c65554cb734270872b72dadd6/server.jar"
        if(jVersion == 5):
            print("\tVersione JAR: 1.15.2\n")
            url = "https://launcher.mojang.com/v1/objects/4d1826eebac84847c71a77f9349cc22afd0cf0a1/server.jar"
        
    if(jType == 2):
        if(jVersion == 1):
            print("\tVersione JAR: 1.8.9\n")
            url = "https://cdn.getbukkit.org/spigot/spigot-1.8.8-R0.1-SNAPSHOT-latest.jar"
        if(jVersion == 2):
            print("\tVersione JAR: 1.12.2\n")
            url = "https://cdn.getbukkit.org/spigot/spigot-1.12.2.jar"
        if(jVersion == 3):
            print("\tVersione JAR: 1.13.2\n")
            url = "https://cdn.getbukkit.org/spigot/spigot-1.13.2.jar"
        if(jVersion == 4):
            print("\tVersione JAR: 1.14.4\n")
            url = "https://cdn.getbukkit.org/spigot/spigot-1.14.4.jar"
        if(jVersion == 5):
            print("\tVersione JAR: 1.15.2\n")
            url = "https://cdn.getbukkit.org/spigot/spigot-1.15.2.jar"
    print("\tRAM dedicata: "+str(dRam)+"MB")
    print("\n\tContinuare con la creazione del server? Scegliendo y accetti l'eula di Mojang.")
    print("\tScegliendo n cancellerai la creazione del server.")
    print("\tScegli tra y / n\n")
    s = str(input("\t>>>"))
    if(s == "n"):
        return 0
    elif (s == "y"):
        clear()
        print("Creazione del server avviata.")
        os.system("md "+nome)
        filename = wget.download(url=url)
        os.system("move "+filename+" "+nome)
        os.system("echo java -Xmx"+str(dRam)+"M -Xms"+str(dRam)+"M -jar "+filename+" nogui>serverStarter.bat")
        os.system("move serverStarter.bat "+nome)
        os.system("echo eula=true>eula.txt")
        os.system("move eula.txt "+nome)
        print("Creazione del server completata.")
        os.system("timeout /t 5 /nobreak")
        clear()
        print("\tIl server e' stato creato all'interno della cartella chiamata "+nome+".")
        print("\tPer avviare il server aprire il file chiamato serverStarter all'interno")
        print("\tdella cartella.")
        print("\tLa cartella puo' essere spostata ovunque perche' contiene")
        print("\ttutti i file necessari al corretto funzionamento del server.\n")
        print("\tPremere un tasto qualsiasi per continuare")
        os.system("pause>nul")

while True: 
    clear()
    scelta = menu()
    if(scelta == 0):
        quit()
    else:
        if(scelta == 1):
            crea()
        if(scelta == 2):
            print("\tNon ancora implementato.")