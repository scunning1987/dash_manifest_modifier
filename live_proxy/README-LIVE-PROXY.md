# DASH Manifest Modifier - LIVE PROXY
[*Back to main README*](../README.md)
## Overview
This variation of the DASH modifier script is designed to be proxy live requests from a client and modify the manifest from the origin before serving to the client.

![](images/dash-manifest-live-proxy-architecture.png?width=80pc&classes=border,shadow)

## Prerequisites
* You need to have an AWS account
* Your IAM user/role must be able to create: API Gateway endpoint, AWS Lambda function
* Download the Lambda Function zip file from [here](./dash-manipulator-lambda.zip)
* Download the API Gateway endpoint json file from [here](./api_gateway_template.json)

## Deployment Instructions

### AWS Lambda Function
1. Login to the AWS console
2. Navigate to the AWS Lambda service console
3. Select **Create function**
4. Give the function a name, for example: **dash-manifest-modifier**
4. For runtime, select: Python 3.8
5. Select **Create function**
6. In the function overview page, select the **Upload** button from the Code Block section
7. Navigate to the Lambda zip file you downloaded from the prerequisites section
8. Import the Zip!
9. Go to the Configuration tab, then Environment Variables. Select the **Edit** button
10. Add the key (case sensitive) : ORIGIN
11. Add your origin base url, for example: `https://abcdef.egress.mediapackage-vod.us-west-2.amazonaws.com`
12. Select the **Save** button

### Amazon API Gateway
1. Login to the AWS console
2. Select **Create API**
3. Under API Type, select **REST API - Import**
4. In the *Import from Swagger or Ipen API3* section, select **Select Swagger File**
5. Browse to the api gateway json file you downloaded earlier
6. Select the **Import** button
7. Under Resources, select the **Any** method, then select the **Integration Request** box
8. Select the edit pencil next to **Lambda Region**, and select your Lambda region, , then select the tick box to the right of the field
9. Select the edit pencil next to **Lambda Function**, delete the text in this field and start typing the name of your Lambda function until it auto-populates, then select the tick box to the right of the field
10. Now select the 'root slash' `/` under the Resources pane, then select the **Actions** button, then **Deploy API**
11. In the popup box that appears, select a new deployment stage, and give it name **v1**, then select the **Deploy** button
12. Retrieve your Invoke URL by selecting the **Stages** pane, then expand your *v1* stage until you see methods under the `/{proxy+}` Resource, select the GET method, and note the Invoke URL that appears. It will look something like:
```
 Invoke URL: https://58xolfcabc.execute-api.us-west-2.amazonaws.com/v1/{proxy+} 
```

### Caching
This guide doesn't discuss manifest caching, but it can and should be done to save unnecessary API Gateway transactions and AWS Lambda invocations. Amazon API Gateway has built-in [caching](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html). Alternatively, you could use a CDN like [CloudFront](https://aws.amazon.com/cloudfront/) in front of your API Gateway endpoint and apply caching there.

## How To Use

### The API Gateway Proxy
When you deploy your API Gateway stage, the invoke URL will look something like:
```
https://wnbche8zd1.execute-api.us-west-2.amazonaws.com/vod/{proxy+}
```

The URL to your video assets may look something like:
```
https://abcdef.cloudfront.net/12345/vod1/index.mpd
```

In order to use the proxy, send every manifest request to the API Gateway Invoke URL, and replace the `{proxy+}` with the URL path to your video asset. Using the above 2 URL's as an example, this is what your proxy request would become:
```
https://wnbche8zd1.execute-api.us-west-2.amazonaws.com/vod/12345/vod1/index.mpd
```

The API Gateway endpoint invokes the Lambda function, and sends the client request path as an event argument to the function. 

Lambda then uses the path argument along with a predefined origin URL to fetch the manifest from the origin.

Alternatively, the requester can override the predefined/assumed origin url by adding an (?origin=xxx) query parameter to the request URL. 
If a query parameter is used, the origin url must be HTML encoded, ie: 
```
https://wnbche8zd1.execute-api.us-west-2.amazonaws.com/vod/12345/vod1/index.mpd?origin=https%3A%2F%2Fabcdef.cloudfront.net
```

### Modifying the Lambda function

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

Once you're finished customizing the function, select the Orange **Deploy** button to save changes immediately.