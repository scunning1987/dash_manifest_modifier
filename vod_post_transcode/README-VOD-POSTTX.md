# DASH Manifest Modifier - VOD POST TRANSCODE
[*Back to main README*](../README.md)
## Overview
This variation of the DASH modifier script is designed to run as a post-transcode script, triggered by the transcoder as a post-processing event.

[insert pic here]

## Prerequisites
* prereq 1
* prereq 2

## Deployment Instructions

### Installing Python 3
First, install some prerequisites via yum:
```
sudo su
yum -y install gcc openssl-devel bzip2-devel sqlite-devel
```

Download and install Python 3:
```
cd /tmp/
wget https://www.python.org/ftp/python/3.6.6/Python-3.6.6.tgz
tar xzf Python-3.6.6.tgz
cd Python-3.6.6
./configure --enable-optimizations
sudo make altinstall
```

Create new symbolic link to Python 3:
```
mv /usr/bin/python /usr/bin/python-deprecated
ln -sfn /usr/local/bin/python3.6 /usr/bin/python
```

Edit bashrc file for user Elemental:
```
vi ~/.bashrc

[ADD BELOW LINES AT END OF FILE]
# User specific aliases and functions
alias python='/usr/bin/python3.6'
```

...and do the same for root:
```
sudo vi ~/.bashrc

[ADD BELOW LINES AT END OF FILE]
# User specific aliases and functions
alias python='/usr/bin/python3.6'
```

Run the following command so that the changes take effect immediately
```
. ~/.bashrc
```

### Installing XMLtoDICT using pip
Install PIP
```
python get-pip.py
```

Install XMLtoDict
```
pip install xmltodict
```

### Moving the script to the transcode nodes
1. Download the python [script](./dash_manifest_modifier.py)
2. Copy the python file to the Elemental Server node(s). Here's an example showing scp:
`# scp dash_manifest_modifier.py elemental@10.10.10.10:/home/elemental/`
3. SSH into the node as user elemental
4. Change permissions on the script so it can be executed:
`# chmod 755 dash_manifest_modifier.py`
5. Move the file to the public scripts directory:
`# mv dash_manifest_modifier.py /opt/elemental_se/web/public/scripts/`

### Configuring transcode job to use script
1. Open the Elemental Server UI, create a new job
2. Define your input and output parameters
3. Under **Global Processors**, switch the Post Processing processor to ON
4. Under the script field, enter or browse to the script file

![](./images/elemental-server-ui-post-processing.png?width=80pc&classes=border,shadow)

5. Create/Run the transcode job

## How To Use/Modify

This is how you modify/tweak the script to only edit the elements and attributes that you nened to...

To navigate to an element :  <MPD><element><subelement>value</subelement></element></MPD>

it's done like this: 
```
mpddoc['MPD']['element']['subelement'] = "newvalue"
```

To navigate to an attribute : <MPD><element><subelement id='100'>value</subelement></element></MPD>

... it's done like this:

```
mpddoc['MPD']['element']['subelement']['@id'] = "200"
```

To add elements/attributes, there is an example in the Lambda function already for Accessibility, it's pasted here also, the '###' indicate my comments inline:

```
a = mpddoc['MPD']['Period']['AdaptationSet'] ### This is of how to browse to an AdaptationSet
a['Role'] = {} ### This is creating a new Element called 'Role' <Role></Role>
a['Role']['@schemeIdUri'] = "urn:mpeg:dash:role:2011" ### This is adding an attribe to the element <Role schemeIdUri="urn:mpeg:dash:role:2011"></Role>
a['Role']['@value'] = "main" ### This is adding an attribe to the element <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"></Role>
if a['@mimeType'] == "video/mp4":
  a['Accessibility'] = {} ### This is creating a new Element called 'Accessibility' <Accessibility></Accessibility>
  a['Accessibility']['@schemeIdUri'] = "urn:scte:dash:cc:cea-608:2015" ### This is adding an attribute to the element
  a['Accessibility']['@value'] = "CC1=eng" ### This is adding an attribute to the element
```

To delete elements from the DASH Manifest,
```
del mpddoc['MPD']['Period']['EventStream']
```
To delete attributes from the DASH manifest:
```
del mpddoc['MPD']['Period']['@start']
```

There are some examples already in the manifest demonstrating some of these actions. There are comments at each section to instruct you where to put your code. Like so:
```
### Modify at the Period Level Here ### START ##

[ PUT YOUR CODE HERE ]

### Modify at the Period Level Here ### END
```

Example 1: At the MPD level, overriding the MPD 'profiles' level produced by the Packager:
```
        ### Modify at the MPD Level Here ### START
        # EXAMPLE : mpddoc['MPD']['@attribute'] == XX
        
        try:
            mpddoc['MPD']['@profiles'] = "urn:mpeg:dash:profile:isoff-live:2011"
        except Exception as e:
            manifest_modify_exceptions.append("Can't change profile attribute value : %s" % (e))
        
        ### Modify at the MPD Level Here ### END
```

Example 2: At the Period level, removing the EventStream element and start attribute:
```
            ### Modify at the Period Level Here ### START
            ## p['attribute']
            try:
                del p['@start']
            except Exception as e:
                manifest_modify_exceptions.append("Period %s : Unable to remove start attribute : %s" % (period,e))
            try:
                del p['EventStream']
            except Exception as e:
                manifest_modify_exceptions.append("Period %s : Unable to remove EventStream element : %s" % (period,e))
        
            ### Modify at the Period Level Here ### END
```

Example 3:  At the Adaptation Set level. Overriding SegmentAlignment attribute value, and adding Accessibility elements
```
                ### Modify at the AdaptationSet Level Here ### START
                ## a['attribute']
                try:
                    a['@segmentAlignment'] = "true"
                except Exception as e:
                    manifest_modify_exceptions.append("Period %s - AdaptationSet %s : Unable to change segmentAlignment value : %s" % (period,adaptationset,e))
        
                try: # hard-code CC accessibility elements
                    a['Role'] = {}
                    a['Role']['@schemeIdUri'] = "urn:mpeg:dash:role:2011"
                    a['Role']['@value'] = "main"
                    if a['@mimeType'] == "video/mp4":
                        a['Accessibility'] = {}
                        a['Accessibility']['@schemeIdUri'] = "urn:scte:dash:cc:cea-608:2015"
                        a['Accessibility']['@value'] = "CC1=eng"
                except Exception as e:
                    manifest_modify_exceptions.append("Period %s - AdaptationSet %s : Unable to add Closed Caption Elements : %s" % (period,adaptationset,e))

        
                ### Modify at the AdaptationSet Level Here ### END
```

In each 'try' block, there is an 'exception' block, designed to catch errors. Exceptions don't necessarily have to exit the function, and in this case all my code is doing is logging the exception to an error list. When the manifest modification is complete, any exceptions get written to the log or printed to the console. You can customize this how you like.. Just remember to put each add/edit/delete inside its own try-catch blocks, as shown in the above Adaptation Set example.