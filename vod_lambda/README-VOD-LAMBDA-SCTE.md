# DASH Manifest Modifier - VOD LAMBDA
[*Back to main README*](../README.md)
## Overview
This variation of the DASH modifier script is designed to run on AWS Lambda, and should be triggered via a CloudWatch event (on the completion of an AWS Elemental MediaConvert transcode job).

The Lambda function will inspect the SCC XML that was submitted with the MediaConvert job and use this to add in the ad signaling information required by downstream ad insertion applications, such as MediaTailor. The function also collapses the multiple Period format of the manifest (if it was constructed that way) and places all add break information inside a single `<EventStream>` element at the top of the new manifest that gets written.


![](images/dash-manifest-vod-lambda-architecture.png?width=80pc&classes=border,shadow)

## Prerequisites

* You need to have an AWS account
* Your IAM user/role must be able to create: AWS Lambda function, IAM Role/Policy, Amazon CloudWatch Rule
* MediaConvert will be the transcoder used for this workflow
* Download the Lambda Function zip file from [here](scripts/dash_esam_single_period_w_eventstream.zip)

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

Add your AWS Lambda function as a target of the event, give the event trigger a name and save!

## How To Use
The script will now run whenever a MediaConvert job completes and meets the event pattern specified in our CloudWatch event rule.

By default, the script is designed to write a new manifest file, using the existing name but with a **-dai** suffix as shown below in the S3 bucket browser:

![](images/dash-manifest-vod-scte35-s3.png?width=80pc&classes=border,shadow)


Here's a manifest snippet of what you can expect to see at the top of the newly written manifest (note the EventStream element and child Event elements):

```
<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="urn:mpeg:dash:schema:mpd:2011" xmlns:cenc="urn:mpeg:cenc:2013" xsi:schemaLocation="urn:mpeg:dash:schema:mpd:2011 http://standards.iso.org/ittf/PubliclyAvailableStandards/MPEG-DASH_schema_files/DASH-MPD.xsd" type="static" minBufferTime="PT6S" profiles="urn:mpeg:dash:profile:isoff-main:2011" mediaPresentationDuration="PT1H28M11.733S" xmlns:scte35="urn:scte:scte35:2013:xml">
	<Period start="PT0.00S" duration="PT88M11.72S" id="1">
		<EventStream timescale="90000" schemeIdUri="urn:scte:scte35:2013:xml">
			<Event timescale="90000" duration="2700000" presentationTime="57469949">
				<scte35:SpliceInfoSection protocolVersion="0" tier="4095">
					<scte35:TimeSignal>
						<scte35:SpliceTime ptsTime="57469949"/>
					</scte35:TimeSignal>
					<scte35:SegmentationDescriptor segmentationEventId="1" segmentationEventCancelIndicator="false" segmentationDuration="2700000">
						<scte35:DeliveryRestrictions webDeliveryAllowedFlag="false" noRegionalBlackoutFlag="false" archiveAllowedFlag="true" deviceRestrictions="3"/>
						<scte35:SegmentationUpid segmentationUpidType="12" segmentationUpidLength="0" segmentationTypeId="52" segmentNum="0" segmentsExpected="1"/>
						<scte35:BreakDuration duration="2700000"/>
					</scte35:SegmentationDescriptor>
				</scte35:SpliceInfoSection>
			</Event>
			<Event timescale="90000" duration="2700000" presentationTime="57469949">
				<scte35:SpliceInfoSection protocolVersion="0" tier="4095">
					<scte35:TimeSignal>
						<scte35:SpliceTime ptsTime="57469949"/>
					</scte35:TimeSignal>
					<scte35:SegmentationDescriptor segmentationEventId="1" segmentationEventCancelIndicator="false" segmentationDuration="2700000">
						<scte35:DeliveryRestrictions webDeliveryAllowedFlag="false" noRegionalBlackoutFlag="false" archiveAllowedFlag="true" deviceRestrictions="3"/>
						<scte35:SegmentationUpid segmentationUpidType="12" segmentationUpidLength="0" segmentationTypeId="53" segmentNum="0" segmentsExpected="1"/>
						<scte35:BreakDuration duration="2700000"/>
					</scte35:SegmentationDescriptor>
				</scte35:SpliceInfoSection>
			</Event>
		</EventStream>
		<AdaptationSet mimeType="video/mp4" frameRate="30000/1001" segmentAlignment="true" subsegmentAlignment="true" startWithSAP="1" subsegmentStartsWithSAP="1" bitstreamSwitching="false">
			<Representation id="1" width="1280" height="720" bandwidth="3000000" codecs="avc1.4d401f">
				<SegmentTemplate media="test720p_$Number%09d$.cmfv" initialization="test720pinit.cmfv" startNumber="1" timescale="90000" presentationTimeOffset="0">
					<SegmentTimeline>
						<S t="0" d="540540" r="105"/>
						<S t="57297240" d="174174"/>
						<S t="57471414" d="96096"/>
						<S t="57567510" d="540540" r="78"/>
						<S t="100270170" d="354354"/>
		                                ...
	</Period>
</MPD>				
```