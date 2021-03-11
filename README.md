# XDevice<a name="EN-US_TOPIC_0000001083129731"></a>

-   [Introduction](#section15701932113019)
-   [Directory Structure](#section1791423143211)
-   [Constraints](#section118067583303)
-   [Usage](#section2036431583)
-   [Repositories Involved](#section260848241)

## Introduction<a name="section15701932113019"></a>

XDevice, a core module of the OpenHarmony test framework, provides services on which test case execution depends.

XDevice consists of the following sub-modules:

-   **command**: enables command-based interactions between users and the test platform. It parses and processes user commands.
-   **config**: sets test framework configurations and provides different configuration options for the serial port connection and USB connection modes.
-   **driver**: functions as a test case executor, which defines main test steps, such as test case distribution, execution, and result collection.
-   **report**: parses test results and generates test reports.
-   **scheduler**: schedules various test case executors in the test framework.
-   **environment**: configures the test framework environment, enabling device discovery and device management.
-   **testkit**: provides test tools to implement JSON parsing, network file mounting, etc.
-   **resource**: provides the device connection configuration file and report template definitions.
-   **adapter**: adapts the test framework to open-source software.

## Directory Structure<a name="section1791423143211"></a>

```
xdevice
├── config                    # XDevice configuration
│     ├── user_config.xml    # XDevice environment configuration
├── resource                  # XDevice resources
│     ├── tools              # Burning tools
├── src                       # Source code
│     ├── xdevice
├── extension                 # XDevice extension
│     ├── src                # Source code of the extension
│     └── setup.py           # Installation script of the extension
```

## Constraints<a name="section118067583303"></a>

The environment requirements for using this module are as follows:

-   Python version: 3.7.5 or later
-   pySerial version: 3.3 or later
-   Paramiko version: 2.7.1 or later
-   RSA version: 4.0 or later

## Usage<a name="section2036431583"></a>

-   **Installing XDevice**
    1.  Go to the installation directory of XDevice.
    2.  Open the console window and run the following command:

        ```
        python setup.py install
        ```


-   **Installing the extension**
    1.  Go to the installation directory of the XDevice extension.
    2.  Open the console and run the following command:

        ```
        python setup.py install
        ```


-   **Modifying the user\_config.xml file**

    Configure information about your environment in the  **user\_config.xml**  file.

    **1. Configure the environment.**

    -   For devices that support hdc connection, refer to the following note to configure the environment.

        >![](figures/icon-note.gif) **NOTE:** 
        >**ip/port**: IP address and port of a remote device. By default, the parameter is left blank, indicating that the local device \(IP address: 127.0.0.1; port: the one used for hdc startup\) is used as the test device.
        >**sn**: SN of the test devices specified for command execution. If this parameter is set to  **SN1**, only device SN1 can execute the subsequent  **run**  commands. In this case, other devices are set as  **Ignored**  and not involved in the command execution. You can run the  **list devices**  command and check the value of  **Allocation**  to view the  **sn**  values. You can set multiple SNs and separate each two of them with a semicolon \(;\).

    -   For devices that support serial port connection, refer to the following note to configure the environment.

        >![](figures/icon-note.gif) **NOTE:** 
        >**type**: device connection mode. The  **com**  mode indicates that the device is connected through the serial port.
        >**label**: device type, for example,  **wifiiot**
        >**serial**: serial port
        >-   **serial/com**: serial port for local connection, for example,  **COM20**
        >-   **serial/type**: serial port type. The value can be  **cmd**  \(serial port for test case execution\) or  **deploy**  \(serial port for system upgrade\).
        >    For the open-source project, the  **cmd**  and  **deploy**  serial ports are the same, and their  **com**  values are the same too.
        >**serial/baud\_rate, data\_bits, stop\_bits**  and  **timeout**: serial port parameters. You can use the default values.


    **2. Set the test case directory.**

    **dir**: test case directory

    **3. Mount the NFS.**

    >![](figures/icon-note.gif) **NOTE:** 
    >**server**: NFS mounting configuration. Set the value to  **NfsServer**.
    >**server/ip**: IP address of the mounting environment
    >**server/port**: port number of the mounting environment
    >**server/username**: user name for logging in to the server
    >**server/password**: password for logging in to the server
    >**server/dir**: external mount path
    >**server/remote**: whether the NFS server and the XDevice executor are deployed on different devices. If yes, set this parameter to  **true**. Otherwise, set it to  **false**.

-   **Specify the task type.**
-   **Start the test framework.**
-   **Execute test commands.**

    Test framework commands can be classified into three groups:  **help**,  **list**, and  **run**. Among them,  **run**  commands are most commonly used in the instruction sequence.

    **help**

    Queries help information about test framework commands.

    ```
    help:
         Use help to get information.  
    usage:
         run:  Display a list of supported run commands.
         list: Display a list of supported devices and task records.
    Examples:
         help run
         help list
    ```

    >![](figures/icon-note.gif) **NOTE:** 
    >**help run**: displays the description of  **run**  commands.
    >**help list**: displays the description of  **list**  commands.

    **list**

    Displays device information and related task information.

    ```
    list:
         Display device list and task records.  
    usage:
          list
          list history
          list <id>  
    Introduction:
         list:         Display the device list.
         list history: Display historical records of a series of tasks.
         list <id>:    Display historical records of tasks with the specified IDs.
    Examples:
         list
         list history
         list 6e****90
    ```

    >![](figures/icon-note.gif) **NOTE:** 
    >**list**: displays device information.
    >**list history**: displays historical task information.
    >**list <id\>**: displays historical information about tasks with specified IDs.

    **run**

    Executes test tasks.

    ```
    run:
         Execute the selected test cases.
         The command execution process includes use case compilation, execution, and result collection.
    usage: run [-l TESTLIST [TESTLIST ...] | -tf TESTFILE
                [TESTFILE ...]] [-tc TESTCASE] [-c CONFIG] [-sn DEVICE_SN]
                [-rp REPORT_PATH [REPORT_PATH ...]]
                [-respath RESOURCE_PATH [RESOURCE_PATH ...]]
                [-tcpath TESTCASES_PATH [TESTCASES_PATH ...]]
                [-ta TESTARGS [TESTARGS ...]] [-pt]
                [-env TEST_ENVIRONMENT [TEST_ENVIRONMENT ...]]
                [-e EXECTYPE] [-t [TESTTYPE [TESTTYPE ...]]]
                [-td TESTDRIVER] [-tl TESTLEVEL] [-bv BUILD_VARIANT]
                [-cov COVERAGE] [--retry RETRY] [--session SESSION]
                [--dryrun] [--reboot-per-module] [--check-device]
                [--repeat REPEAT]
                action task  
    Specify tests to run.
      positional arguments:
       action                Specify the action to do.
       task                  Specify the task name, such as ssts, acts, and hits.
    ```

    >![](figures/icon-note.gif) **NOTE:** 
    >The structure of a basic  **run**  command is as follows:
    >```
    >run [task name] -l module1;moudle2
    >```
    >**task name**: task type. This parameter is optional. Generally, the value is  **ssts**,  **acts**, or  **hits**.
    >**-l**: test cases to execute. Use semicolons \(;\) to separate each two test cases.
    >**module**: module to test. Generally, there is a  **.json**  file of the module in the  **testcases**  directory.
    >In addition, other parameters can be attached to this command as constraints. Common parameters are as follows:
    >**-sn**: specifies the devices for test case execution. If this parameter is set to  **SN1**, only device SN1 executes the test cases.
    >**-c**: specifies a new  **user\_config.xml**  file.
    >**-rp**: indicates the path where the report is generated. The default directory is  **xxx/xdevice/reports**. Priority of a specified directory is higher than that of the default one.
    >**-tcpath**: indicates the environment directory, which is  **xxx/xdevice/testcases**  by default. Priority of a specified directory is higher than that of the default one.
    >**-respath**: indicates the test suite directory, which is  **xxx/xdevice/resource**  by default. Priority of a specified directory is higher than that of the default one.
    >**--reboot-per-module**: restarts the device before test case execution.

-   **View the execution result.**

    After executing the  **run**  commands, the test framework displays the corresponding logs on the console, and generates the execution report in the directory specified by the  **-rp**  parameter. If the parameter is not set, the report will be generated in the default directory.

    ```
    Structure of the report directory (the default or the specified one)
         ├── result # Test case execution results of the module
         │     ├── module name.xml
         │     ├──  ... 
         │      
         ├── log # Running logs of devices and tasks
         │     ├── device 1.log
         │     ├── ...
         │     ├── task.log
         ├── summary_report.html # Visual report
         ├── summary_report.html # Statistical report
         └── ...
    ```


## Repositories Involved<a name="section260848241"></a>

test\_xdevice

test\_xdevice\_extension

