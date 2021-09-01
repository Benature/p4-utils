# P4-Utils Virtual Machine

Although P4-Utils can be installed directly on your system, running P4-Utils in a completely separated
environment can be beneficial: in this way, installation and execution errors, that may arise, will not
affect the whole system. For this reason, **we recommend using one of the VM methods that we provide**.
In addition, since P4-Utils is only available on Linux, other OS users can run it in a Linux virtual machine.

We provide two different solutions for the P4-Utils VM and both are supported by a wide range of 
operating systems:

- [VirtualBox](https://www.virtualbox.org/)
- [QEMU](https://www.qemu.org/)

You can choose to download and use one of our [preconfigured VMs](#use-our-preconfigured-vm) or to
[build it by yourself](#build-your-own-vm).

> **Important**  
> Whether you are building your own VM or you are using the preconfigured images, you still
> need to install one of the above virtualizer according to your VM choice.

## Build your own VM

To get started, you need to install the required software:

- [VirtualBox](https://www.virtualbox.org/) or [QEMU](https://www.qemu.org/)
- [Packer](https://www.packer.io/)

> **Note**  
> Packer is a handy framework designed to automatically build custom VM images.

Clone the P4-Utils repository:

```
git clone https://github.com/nsg-ethz/p4-utils
```

Go to the Packer configurations folder:

```
cd p4-utils/vm
```

If you want to build the *VirtualBox VM*, execute:

```
./build-virtualbox.sh [--cpus 4] [--disk_size 25000] [--memory 4000] [--vm_name p4] [--username p4] [--password p4]
```

On the other hand, if you prefer the *QEMU VM*, run:

```
./build-qemu.sh [--cpus 4] [--disk_size 25000] [--memory 4000] [--vm_name p4] [--username p4] [--password p4]
```

According to the commands shown above, some parameters can be passed to the building scripts
to customize the VM:

- ``--cpus`` specifies the **number of cores** to use,
- ``--disk_size`` is the **size of the disk** reserved by the VM in MBytes,
- ``--memory`` is the amount of **RAM** to assign to the VM in MBytes,
- ``--vm_name`` is the **name of the VM**,
- ``--username`` is the **login username**,
- ``--password`` is the **login password**.

> **Attention**  
> The default VMs configuration parameters are shown above between square brakets. If you do not 
> specify anything, they will be used to build your VM. However, please pass to the scripts the
> parameters that best fit your needs.

## Use our preconfigured VM

To download our preconfiugred VMs, please click on the folllwing links:

- [*VirtualBox VM*](#)
- [*QEMU VM*](#)
