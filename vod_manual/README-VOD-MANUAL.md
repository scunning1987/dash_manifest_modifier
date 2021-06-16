# DASH Manifest Modifier - VOD MANUAL
[*Back to main README*](../README.md)
## Overview
This variation of the DASH modifier script is designed to be standalone, executed from the command line to modify a manifest that's reachable on the network, and overwrite the original.

[Script contents](./dash_manifest_modifier.py)

## Required
* Python 3
* PIP
* XMLtoDict

## Deployment Instructions
* You will need Python 3.7 or 3.9 to run this script. Find out how to install/upgrade Python for your platform [here](https://www.python.org/)
* You will need to install pip , [here's how](https://pip.pypa.io/en/stable/installing/)
* You will need to install xmltodict, [here's how](https://pypi.org/project/xmltodict/)

## How To Use/Modify

### Run the script
Execute the script and pass 1 argument, the NFS location to the manifest:
```
python dash_manifest_modifier.py /media/dash/asset1/index.mpd
```

### Modify the script
This is how you modify/tweak the script to only edit the elements and attributes that you need to...

To navigate to an element :  `<MPD><element><subelement>value</subelement></element></MPD>`

it's done like this:
```
mpddoc['MPD']['element']['subelement'] = "newvalue"
```

To navigate to an attribute : `<MPD><element><subelement id='100'>value</subelement></element></MPD>`

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