# Auto Install Script For OpenMediaVault/Debian/Ubuntu 20,22 24.02

> > [!CAUTION]
> This installation method is not supported or maintained by the ARM Developers.
> For full support and continued maintenance,
> we recommend installing ARM via the supported [Docker Container](https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/docker).
> This installation method was developed for those that wish to use ARM without Docker.
>
> **Use at your own risk**

This is **not recommended** for first time installations. This was only really intended to be used to reinstall on an environment you know works fully with ARM

**contrib repositories are required!**

## For the attended install use:
 ```
sudo apt install wget
wget https://raw.githubusercontent.com/automatic-ripping-machine/automatic-ripping-machine/main/scripts/installers/DebianInstaller.sh
sudo chmod +x DebianInstaller.sh
sudo ./DebianInstaller.sh
sudo chmod +x /opt/arm/scripts/update_key.sh
 ```
 ```reboot``` 
 to complete installation.


## Post install

### Setting up the database
The ARM UI creates its database on its first start. It also creates the `admin` account with a random password
and prints it once to the ARM UI's log. Find it with

```
sudo journalctl -u armui | grep -A3 'ARM first run'
```

Sign in as `admin` with that password, then change it (Change admin password). Installs set up before this
change keep their existing password. `/setup` is only available while no user exists.


Alternatively, you can insert a disc or trigger it manually by running 
`/usr/bin/python3 /opt/arm/arm/ripper/main.py -d sr0 | at now` in a terminal/ssh

### File Permissions 

Make sure arm has write permission to the folder you have selected in the arm.yaml. If you haven't changed the arm.yaml it will be `/home/arm`

For example `sudo chmod -R 777 /home/arm` **Please check/change these, this is for example only!**