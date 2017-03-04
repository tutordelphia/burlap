Tutorial
========

This short tutorial will guide you through basic Burlap usage, such as starting a project, adding a custom Satchel, and deploying your changes to a server.

## Installation

Open a terminal to an empty folder and run:

    virtualenv .env
    . .env/bin/activate
    pip install burlap

## Initializing your project

Burlap includes an administrative command called `burlap-admin.py` which is used for performing some basic initialization and changes to your project.

To create a new burlap-managed project, run:

    burlap-admin.py skel myproject

This will create a structure like:

    <project root>
    ├── roles
    |   └── all
    |       ├── settings.yaml
    |       └── pip-requirements.txt
    |    
    ├── src
    |
    └── fabfile.py

The `roles` folder is where Burlap stores settings for different server classifications, specifically in a file named `settings.yaml`. If a file called `settings_local.yaml` is present, this will automatically be included. This is useful in adding sensitive settings, like passwords, which you don't want to commit to source control.

The `src` folder is where you application's custom source code will be located. This folder name isn't required, and can be changed to whatever you want.

Finally, the `fabfile.py` file is a standard [Fabric](http://www.fabfile.org/) configuration file that will allow you to use Burlap's built-in tasks.

## Creating roles

It's customary to have separate servers for development and production, so lets create two new roles to represent this, by running:

    burlap-admin.py add-role prod dev

Your structure should now look like:

    <project root>
    ├── roles
    |   ├── all
    |   |   ├── settings.yaml
    |   |   └── pip-requirements.txt
    |   |
    |   ├── dev
    |   |   └── settings.yaml
    |   |
    |   └── prod
    |       └── settings.yaml
    |    
    ├── src
    |
    └── fabfile.py

## Running tasks

Burlap includes a ton of built-in commands for managing common services.

To see a list of all these tasks, run:

    fab --list
    
## Creating satchels

Burlap organizes units of functionality into a "satchel".

To understand the structure of a satchel, let's create one for managing user permissions. Start by running:

    burlap-admin.py create-satchel UserPerm

This will create a new `satchels` folder and populate it with a stub satchel file called `userperm.py`. 

Inspect the file. You'll see it contains a subclass of the `Satchel` class, and contains three methods.

Every satchel should contain at least two basic methods, `set_defaults`, which defines the satchels custom environment variables, and `configure`, which is run by burlap during deployments to apply the satchel's functionality to the server. Burlap will automatically keep track of changes in satchel settings between deployments, and only run the satchel's `configure` method when a change has been detected.

For this example, an additional example task has been added called `helloworld`. Try to run this with:

    fab dev userperm.helloworld

You should see the text "helloworld" printed to the screen.

The `Satchel` class exposes most of Fabric's operations via class methods, so you can reference `sudo`, `run` and `local` via `self.sudo`, `self.run` and `self.local` respectfully.

Each of these methods has a wrapper around them that extends them to include some additional functionality.

1. Passing them a `dryrun=1` parameter will cause them to only output their command without running it on the server.
2. Passing them a `verbose=1` parameter will cause `self.verbose` to be set to True, which can be used to enable additional output.
3. The command string passed supports a templating language based off of Python's bracket notation. Instead of hard-coding paths and other values into the command, you can reference local Satchel settings, settings in other Satchels, or global settings.

Let's try each of these in turn.

Run:

    fab dev userperm.helloworld:dryrun=1
    
You should see the `echo` command printed to the screen, like before, but not the result of the echo.

Now run:

    fab dev userperm.helloworld:verbose=1
    
You should see an additional note printed.

Now change the value of `self.env.helloworld_text` in the Satchel file to "hello {user}" and re-run:

    fab dev userperm.helloworld

You should see your new text printed, but now including your username.

As you can see by the empty `configure` method, this Satchel doesn't do much else. How a Satchel's changes are applied to the server is up to each Satchel, and this can be simple or complex depending on the application the Satchel is managing.

## Deploying changes

Burlap provides a deployment mechanism via the `deploy.*` series of commands.

To deploy all changes to a target role, run:

    fab prod deploy.run
    
This will first show a list of Satchels that have changes detected, and prompt you to confirm. If you select "yes", it will run the `configure` task on all the listed Satchels, and then record the current environment state for future comparison.
