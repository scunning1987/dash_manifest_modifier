# DASH Manifest Modifier - VOD LAMBDA
[*Back to main README*](../README.md)
## Overview
This variation of the DASH modifier script is designed to run on AWS Lambda, and should be triggered via a CloudWatch event (on the completion of an AWS Elemental MediaConvert transcode job).

![](images/dash-manifest-vod-lambda-architecture.png?width=80pc&classes=border,shadow)

## Prerequisites

* You need to have an AWS account
* Your IAM user/role must be able to create: AWS Lambda function, IAM Role/Policy, Amazon CloudWatch Rule
* MediaConvert will be the transcoder used for this workflow
* Download the Lambda Function zip file from [here]()

## Deployment Instructions

### AWS Lambda Function
1. Login to the AWS console
2. Navigate to the AWS Lambda service console
3. Select **Create function**
4. Give the function a name, for example: **dash-manifest-modifier**
5. For runtime, select: Python 3.8
6. Select **Create function**
7. In the function overview page, select the **Upload** button from the Code Block section
8. Navigate to the Lambda zip file you downloaded from the prerequisites section
9. Import the Zip!
10. Go to the Configuration tab, then General configuration. Select the **Edit** button and change the timeout value to 30 seconds and Save
11. Next, go to Permissions, under Execution role, select the Role hyperlink for the IAM role that was created with this Lambda function

*Note; this will open a new tab in your browser to the IAM Console...*

**For this exercise, we'll give the AWS Lambda function full access to your S3 bucket, as the function needs to READ the DASH manifest, as well as WRITE/PUT an updated manifest back to S3. The access can be further restricted with a tighter policy. See the [AWS policy generator](https://awspolicygen.s3.amazonaws.com/policygen.html) to build a more restricted policy**

13. In the role Summary, under the Permissions tab select **Add inline policy**
14. In the Create policy wizard, select the JSON tab, then paste the below contents into the code block. **Replace "mybucket" with the name of your S3 buckeet**
```
{
"Version": "2012-10-17",
"Statement": [
{
"Sid": "VisualEditor0",
"Effect": "Allow",
"Action": "s3:*",
"Resource": "arn:aws:s3:::mybucket"
}
]
}
```
15. Select the **Review policy** button, give the policy a name, ie. FullAccessToS3BucketX, then select the **Create policy** button
16. You can now close the IAM console tab

### CloudWatch Event
1. Login to your AWS account
2. Navigate to Amazon CloudWatch
3. Expand Events, then Select Rules, followed by the **Create rule** button
4. Under Event source, select **Event Pattern**, then **Build custom event pattern** from the drop-down menu
5. Copy the below json block and paste into the event pattern code block

```
{
  "source": ["aws.mediaconvert"],
  "detail-type": ["MediaConvert Job State Change"],
  "detail": {
    "status": ["COMPLETE"],
    "outputGroupDetails": {
      "type": ["DASH_ISO_GROUP"]
    }
  }
}
```

6. Under Targets, select **Add target**
7. Select **Lambda function** from the target drop-down menu
8. In the Function field, select your Lambda function from the drop-down menu
9. Select the **Configure details** button
10. Give the rule a name, ie. **MediaConvert Completion Event - DASH**, and optionally, a description to further identify the rule
11. Select the **Create rule** button

*Note: From this point on, any MediaConvert job completion events that match the event pattern above will trigger the rule to invoke your Lambda function*

Add your AWS Lambda function as a target of the event, give the event trigger a name and save

## How To Use

This is how you use...