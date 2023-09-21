'''
Copyright (c) 2021 Scott Cunningham

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Summary: This script is designed to parse and modify an MPEG DASH manifest.

Original Author: Scott Cunningham
'''

import json
import boto3
import datetime
import math
import os
import requests
import xmltodict
import re

import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
MANIFESTMODIFY = True
INSERTEMCEVENTS = True

def lambda_handler(event, context):

    LOGGER.info("event : %s" % (str(event)))

    ## CloudWatch Event Trigger

    # event body will be from CloudWatch Event
    event_body = event
    region = event_body['region']
    job_id = str(event_body['detail']['jobId'])

    # S3 client
    s3 = boto3.client('s3')

    '''
    # get the account-specific mediaconvert endpoint for this region
    mediaconvert_client = boto3.client('mediaconvert', region_name=region)
    endpoints = mediaconvert_client.describe_endpoints()

    # add the account-specific endpoint to the client session
    client = boto3.client('mediaconvert', region_name=region, endpoint_url=endpoints['Endpoints'][0]['Url'], verify=True)
    response = client.get_job(Id=job_id)
    job_details = json.loads(json.dumps(response, default = lambda o: f"<<non-serializable: {type(o).__qualname__}>>"))
    '''

    for outputgroup in event['detail']['outputGroupDetails']:
        if outputgroup['type'] == "DASH_ISO_GROUP":
            bucket = outputgroup['playlistFilePaths'][0].split("/",3)[2]
            key = outputgroup['playlistFilePaths'][0].split("/",3)[3]


    data_mpd = s3.get_object(Bucket=bucket, Key=key)

    # Read S3 object response into Variable
    mpd_file = data_mpd['Body'].read()

    ################ FOR USE WITH S3 TRIGGERS #########################
    # s3 = boto3.client('s3')

    # bucket = event['Records'][0]['s3']['bucket']['name']
    # key = event['Records'][0]['s3']['object']['key']

    # if ".mpd" not in key:
    #     LOGGER.error("File does not contain a DASH manifest extension : %s . Exiting..." % (key))
    #     return "File does not contain a DASH manifest extension : %s . Exiting..." % (key)

    # LOGGER.info("Bucket : %s - Key : %s " % (bucket,key))

    # # Perform S3 get object, then read file to variable (mpddoc)
    # try:
    #     data_mpd = s3.get_object(Bucket=bucket, Key=key)
    # except Exception as e:
    #     LOGGER.error("Error getting DASH manifest from S3 : %s " % (e))
    #     return "Error getting DASH manifest from S3 : %s " % (e)

    # # Read S3 object response into Variable
    # mpd_file = data_mpd['Body'].read()
    ################ END --- FOR USE WITH S3 TRIGGERS #############################################

    if INSERTEMCEVENTS:

        # get the account-specific mediaconvert endpoint for this region
        mediaconvert_client = boto3.client('mediaconvert', region_name=region)

        try:
            endpoints = mediaconvert_client.describe_endpoints()
        except:
            raise Exception("Unable to get MediaConvert endpoints, cannot continue...")

        # add the account-specific endpoint to the client session
        client = boto3.client('mediaconvert', region_name=region, endpoint_url=endpoints['Endpoints'][0]['Url'], verify=True)

        try:
            response = client.get_job(Id=job_id)
        except Exception as e:
            LOGGER.error("Unable to get job data from MediaConvert, got exception: %s " % (e))
            raise Exception("Unable to get job data from MediaConvert, got exception: %s " % (e))

        # Get the ESAM Data and put NPTpoints into List
        job_details = json.loads(json.dumps(response, default = lambda o: f"<<non-serializable: {type(o).__qualname__}>>"))
        esam_xml = job_details['Job']['Settings']['Esam']['SignalProcessingNotification']['SccXml']
        esam_doc = xmltodict.parse(esam_xml.replace("\n"," "))

        esam_break_points = []
        esam_break_points_duration = []
        for signal in esam_doc['SignalProcessingNotification']['ResponseSignal']:

            if signal['sig:SCTE35PointDescriptor']['sig:SegmentationDescriptorInfo']['@segmentTypeId'] == "52":
                try:
                    duration_string = signal['sig:SCTE35PointDescriptor']['sig:SegmentationDescriptorInfo']['@duration']

                    # If break is minutes long, convert any M integer to seconds
                    try:
                        duration_m = int(re.search('PT(.+?)M', duration_string).group(1))
                        duration_m_s = duration_m * 60
                    except AttributeError:
                        # PT<>M not found in ESAM duration
                        duration_m_s = 0 # apply your error handling

                    # If break is seconds long, grab the S integer
                    if re.search('PT[0-9]M(.+?)S', duration_string):
                        duration_s = int(re.search('PT[0-9]M(.+?)S', duration_string).group(1))
                    elif re.search('PT(.+?)S', duration_string):
                        duration_s = int(re.search('PT(.+?)S', duration_string).group(1))
                    else: # S is not present, so we'll check if M was specified, and if not we'll do a default duration of 30 seconds
                        if duration_m_s == 0:
                            duration_s = 30
                        else:
                            duration_s = str(0)

                    # Duration of break in seconds
                    break_duration = duration_m_s + duration_s
                except Exception as e:
                    LOGGER.warning("unable to get adbreak duration from ESAM xml, defaulting to 30 seconds. Exception: %s " % (e))
                    break_duration = str(30)

            if signal['sig:SCTE35PointDescriptor']['sig:SegmentationDescriptorInfo']['@segmentTypeId'] == "52":
                esam_break_points_duration.append([signal['@signalPointID'],break_duration])
                esam_break_points.append(signal['@signalPointID'])

        ## Create EventStream Elements
        def adbreakevents(esam_break_points_duration,video_timescale):
            eventstream = []

            #scte_type = [52,53]
            scte_type = [52]
            for break_point in range(0,len(esam_break_points_duration)):
                for stype_number in range(0,len(scte_type)):
                    s_type = scte_type[stype_number]
                    break_info = esam_break_points_duration[break_point]
                    pts_time = int(float(break_info[0]) * float(video_timescale))
                    duration = int(float(break_info[1]) * float(video_timescale))
                    event_id = str(break_point)
                    dash_event_id = break_point + stype_number

                    LOGGER.debug("EventStream PTS time %s " % (str(pts_time)))

                    scte_event = dict()
                    #scte_event['@timescale'] = video_timescale
                    scte_event['@id'] = str(dash_event_id)
                    scte_event['@duration'] = str(duration)
                    scte_event['@presentationTime'] = str(pts_time)
                    scte_event['scte35:SpliceInfoSection'] = {}
                    scte_event['scte35:SpliceInfoSection']['@protocolVersion'] = "0"
                    scte_event['scte35:SpliceInfoSection']['@tier'] = "4095"
                    scte_event['scte35:SpliceInfoSection']['@ptsAdjustment'] = "0"
                    scte_event['scte35:SpliceInfoSection']['scte35:TimeSignal'] = {}
                    scte_event['scte35:SpliceInfoSection']['scte35:TimeSignal']['scte35:SpliceTime'] = {}
                    scte_event['scte35:SpliceInfoSection']['scte35:TimeSignal']['scte35:SpliceTime']['@ptsTime'] = str(pts_time)
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor'] = {}
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@segmentationEventId'] = event_id
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@segmentationEventCancelIndicator'] = "false"
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@segmentationDuration'] = str(duration)
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@autoReturn'] = "true"
                    # scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions'] = {}
                    # scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@webDeliveryAllowedFlag'] = "false"
                    # scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@noRegionalBlackoutFlag'] = "false"
                    # scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@archiveAllowedFlag'] = "true"
                    # scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@deviceRestrictions'] = "3"
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid'] = {}
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentationUpidType'] = "12"
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentationUpidLength'] = "0"
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentationTypeId'] = str(s_type)
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentNum'] = "0"
                    scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentsExpected'] = "1"
                    #scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:BreakDuration'] = {}
                    #scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:BreakDuration']['@autoReturn'] = "true"
                    #scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:BreakDuration']['@duration'] = str(duration)

                    eventstream.append(scte_event)

            return eventstream

            #return adbreakevents(esam_break_points_duration,60000)


    # Use XMLtoDict package to translate XML to JSON Dictionary
    mpddoc = xmltodict.parse(mpd_file)

    manifest_modify_exceptions = []

    timescale = ""

    if MANIFESTMODIFY:

        ### All of the MPD modify/delete actions below are inside TRY blocks
        ### Add or remove more modify/delete/add actions inside individual TRY block
        ### Any exceptions will be caught and displayed in a DEBUG message.
        ### An exception does not cause the workflow to fail

        LOGGER.info("Manifest Modifier: Starting...")

        ### Modify at the MPD Level Here ### START
        # EXAMPLE : mpddoc['MPD']['@attribute'] == XX



        ### Modify at the MPD Level Here ### END

        if isinstance(mpddoc['MPD']['Period'], list):
            periods = len(mpddoc['MPD']['Period'])
            LOGGER.debug("Manifest Modifier: Manifest has %s Periods" % (str(periods)))
            p_layout = "m"
        else:
            periods = 1
            LOGGER.debug("Manifest Modifier: Manifest has %s Periods" % (str(periods)))
            p_layout = "s"
        ### PERIOD
        for period in range(0,periods):
            if p_layout == "s":
                p = mpddoc['MPD']['Period']
            else:
                p = mpddoc['MPD']['Period'][period]

            ### Modify at the Period Level Here ### START
            ## p['attribute']


            ### Modify at the Period Level Here ### END

            ### ADAPTATION SET
            if isinstance(p['AdaptationSet'], list):
                adaptationsets = len(p['AdaptationSet'])
                LOGGER.debug("Manifest Modifier: Period %s has %s AdaptationSets" % (str(period),str(adaptationsets)))
                a_layout = "m"
            else:
                adaptationsets = 1
                a_layout = "s"
            for adaptationset in range(0,adaptationsets):
                LOGGER.debug("Manifest Modifier: Iterating through AS %s " % (str(adaptationset)))
                if a_layout == "s":
                    a = p['AdaptationSet']
                else:
                    a = p['AdaptationSet'][adaptationset]


                try: # insert ad break elements after getting timescale

                    # get Timescale
                    if 'video' in a['@mimeType']:
                        if len(timescale) < 1:
                            timescale = a['SegmentTemplate']['@timescale']

                except:
                    LOGGER.info("Couldnt get timescale, it wasnt in adaptationset/segmenttemplate/@timescale, setting to zero to alert you to fix the script")
                    timescale = 0

                ### Modify at the AdaptationSet Level Here ### START
                ## a['attribute']

                #  ### EXAMPLE:
                # try: # hard-code CC accessibility elements
                #     a['Role'] = {}
                #     a['Role']['@schemeIdUri'] = "urn:mpeg:dash:role:2011"
                #     a['Role']['@value'] = "main"
                #     if a['@mimeType'] == "video/mp4":
                #         a['Accessibility'] = {}
                #         a['Accessibility']['@schemeIdUri'] = "urn:scte:dash:cc:cea-608:2015"
                #         a['Accessibility']['@value'] = "CC1=eng"
                # except Exception as e:
                #     manifest_modify_exceptions.append("Period %s - AdaptationSet %s : Unable to add Closed Caption Elements : %s" % (period,adaptationset,e))


                ### Modify at the AdaptationSet Level Here ### END


                ### REPRESENTATION ###
                if isinstance(a['Representation'], list):
                    representations = len(a['Representation'])
                    LOGGER.debug("Manifest Modifier: AdaptationSet %s has %s Representations" % (str(adaptationset),str(representations)))
                    r_layout = "m"
                else:
                    representations = 1
                    LOGGER.debug("Manifest Modifier: AdaptationSet %s has %s Representations" % (str(adaptationset),str(representations)))
                    r_layout = "s"
                for representation in range(0,representations):
                    LOGGER.debug("Manifest Modifier: Iterating through Representation %s " % (str(representation)))
                    if r_layout == "s":
                        r = a['Representation']
                    else:
                        r = a['Representation'][representation]

                    ### Modify at the Representation Level Here ### START
                    ## r['attribute']

                    ### Modify at the Representation Level Here ### END

        if len(esam_break_points) > 0:

            # esam_break_points = []
            # esam_break_points.append("10.010")
            # esam_break_points_duration = []
            # esam_break_points_duration.append(["10.010",0])



            # We are assuming the source is single Period DASH. If it is not, the below compiling of the EventStream element will fail

            subsetexists = False

            try:
                ascopy = mpddoc['MPD']['Period']['AdaptationSet']
            except:
                LOGGER.error("ATTEMPT TO COPY ADAPTATIONSET ELEMENT FAILED: Cannot copy adaptationset object from mpd - this needs investigation")

            try:
                sscopy = mpddoc['MPD']['Period']['Subset']
                subsetexists = True
            except:
                LOGGER.info("ATTEMPT TO COPY SUBSET ELEMENT FAILED: no subset element in Period - nothing to copy - this is normal")

            # Delete from single period mpd
            try:
                mpddoc['MPD']['Period'].pop('AdaptationSet')
            except:
                LOGGER.info("No adaptation set in Period - shouldnt happen")

            try:
                mpddoc['MPD']['Period'].pop('Subset')
            except:
                LOGGER.info("No Subset element in Period - this is quite common and you can ignore")

            try:
                mpddoc['MPD']['Period'].pop('EventStream')
            except:
                LOGGER.info("No existing EventStream element in this Period - this is ok")

            mpddoc['MPD']['@xmlns:scte35'] = "urn:scte:scte35:2013:xml"
            mpddoc['MPD']['Period']['EventStream'] = {}
            mpddoc['MPD']['Period']['EventStream']['@schemeIdUri'] = "urn:scte:scte35:2013:xml"
            mpddoc['MPD']['Period']['EventStream']['@timescale'] = timescale
            mpddoc['MPD']['Period']['EventStream']['Event'] = adbreakevents(esam_break_points_duration,timescale)
            mpddoc['MPD']['Period']['AdaptationSet'] = ascopy

            if subsetexists:
                mpddoc['MPD']['Period']['Subset'] = sscopy

            #return mpddoc

        LOGGER.info("Manifest Modifier: Complete...")
        LOGGER.info("Manifest Modifier: Exceptions during modify : %s " % (str(len(manifest_modify_exceptions))))
        LOGGER.debug("Manifest Modifier - Exceptions caught : %s " % (manifest_modify_exceptions))

        new_mpd = xmltodict.unparse(mpddoc, short_empty_elements=True, pretty=True)
    else:
        new_mpd = mpd_xml_live # no change from original MPD

    LOGGER.info("DASH Manifest Creator: Uploading new DASH manifest to S3")

    key = key[0:-4] + "-new.mpd"
    try:
        s3_put_object_response = s3.put_object(Body=new_mpd, Bucket=bucket, Key=key)
        LOGGER.info("Successfully uploaded new MPD, Bucket: %s, Key: %s" % (bucket,key))
    except Exception as e:
        LOGGER.error("Unable to write new DASH manifest to S3 location, Bucket: %s - Key: %s, Exception: %s" % (bucket,key,e))
        return "ERROR: Unable to write new DASH manifest to S3 location, Bucket: %s - Key: %s, Exception: %s" % (bucket,key,e)

    return {
        'statusCode': 200,
        "headers": {
            "Content-Type": "application/xml"
        },
        'body': new_mpd
    }