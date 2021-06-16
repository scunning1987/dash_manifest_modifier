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
3. Select **Create Function**
4. For programming language, select: Python 3.8
5. IAM service role, create new
6. In the function overview page, select the **Upload** button from the Code Block section
7. Navigate to the Lambda zip file you downloaded from the prerequisites section

### Amazon API Gateway
1. Login to the AWS console
2. Navigate to the Amazon API Gateway console
3. Under the RESTful API section, select **Import**
4. Navigate to the API Gateway json file you downloaded from the prerequisites section


## How To Use

The API Gateway endpoint invokes a Lambda, and sends the client request path as an event argument to the function. 

Lambda then uses the path argument along with a predefined origin URL to fetch the manifest from the origin. 

Alternatively, the requester can override the predefined/assumed origin url by adding an (?origin=xxx) query parameter to the request URL. 
If a query parameter is used, the origin url must be HTML encoded, ie: ```https://apigatewayendpoint.com/path/subpath/manifest.mpd?origin=https%3A%2F%2Fthisistheneworigin.com```
