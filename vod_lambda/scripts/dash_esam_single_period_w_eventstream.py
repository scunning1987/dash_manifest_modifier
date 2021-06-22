import json
import boto3
import datetime
import math
import os
import requests
import xmltodict
import copy
import re

import logging

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
MANIFESTUPDATE="True" # LEAVE THIS VALUE to True

# S3 client
s3 = boto3.client('s3')

def lambda_handler(event, context):


    LOGGER.info("event : %s" % (str(event)))

    ## CloudWatch Event Trigger

    # event body will be from CloudWatch Event
    try:
        region = event['region']
        job_id = str(event['detail']['jobId'])
    except Exception as e:
        LOGGER.error("Got wrong event as a trigger for this function. This function needs to parse event[region] and event[detail][jobid]. This is what we received : %s " % (event))
        raise Exception("Got wrong event as a trigger for this function. This function needs to parse event[region] and event[detail][jobid]. This is what we received : %s " % (event))


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
    except:
        LOGGER.error("Unable to get job data from MediaConvert, got exception: %s " % (e))
        raise Exception("Unable to get job data from MediaConvert, got exception: %s " % (e))

    # Get the ESAM Data and put NPTpoints into List
    job_details = json.loads(json.dumps(response, default = lambda o: f"<<non-serializable: {type(o).__qualname__}>>"))
    esam_xml = job_details['Job']['Settings']['Esam']['SignalProcessingNotification']['SccXml']
    esam_doc = xmltodict.parse(esam_xml.replace("\n"," "))

    esam_break_points = []
    esam_break_points_duration = []
    for signal in esam_doc['SignalProcessingNotification']['ResponseSignal']:
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
        except:
            LOGGER.warning("unable to get adbreak duration from ESAM xml, defaulting to 30 seconds")
            break_duration = str(30)

        if signal['sig:SCTE35PointDescriptor']['sig:SegmentationDescriptorInfo']['@segmentTypeId'] == "52":
            esam_break_points_duration.append([signal['@signalPointID'],break_duration])
            esam_break_points.append(signal['@signalPointID'])


    # Get the MPD and VTT if present
    VTTPRESENT = False
    for outputgroup in event['detail']['outputGroupDetails']:
        if outputgroup['type'] == "CMAF_GROUP":
            bucket = outputgroup['playlistFilePaths'][0].split("/",3)[2]
            key = outputgroup['playlistFilePaths'][0].split("/",3)[3]
        elif outputgroup['type'] == "FILE_GROUP":

            if isinstance(outputgroup['outputDetails'], list):
                outputs = len(outputgroup['outputDetails'])
                o_layout = "m"
            else:
                outputs = 1
                o_layout = "s"

            ### PERIOD
            for output in range(0,outputs):
                if o_layout == "s":
                    o = outputgroup['type']
                else:
                    o = outputgroup['outputDetails'][output]

                final_path_name = '/'.join(o['outputFilePaths'][0].split("/")[-2:])
                if "vtt" in final_path_name or "VTT" in final_path_name or "Vtt" in final_path_name:
                    if ".jpg" not in final_path_name:
                        VTTPRESENT=True
                        vtt_full_no_ext = o['outputFilePaths'][0]
                        vtt_media_path = '/'.join(vtt_full_no_ext.split("/")[-2:])
                        vtt_full =  o['outputFilePaths'][0] + ".vtt"
                ### Get details at the Period Level Here ### START
                ## p['attribute']


    # Name for the new MPD that will supercede the MediaConvert manifest
    new_key = key.replace(".mpd","-dai.mpd")

    # Get Manifest from S3
    try:
        key = event['detail']['outputGroupDetails'][0]['playlistFilePaths'][0].split("/",3)[3]
        data_mpd = s3.get_object(Bucket=bucket, Key=key)
    except Exception as e:
        LOGGER.error("Failed to get manifest from S3, got exception : %s " % (e))
        raise Exception("Failed to get manifest from S3, got exception : %s " % (e))

    # Get VTT File from S3 if present
    if VTTPRESENT:
        LOGGER.info("There is a webVTT file present in the job output, location : %s " % (vtt_full))
        vtt_key = vtt_full.split("/",3)[3]
        try:
            data_vtt = s3.get_object(Bucket=bucket, Key=vtt_key)
            vtt_file = data_vtt['Body'].read()
            vtt_list = vtt_file.decode('utf-8').split("\n\n")
        except Exception as e:
            LOGGER.error("Unable to get WebVTT file from S3, got exception : %s " % (e))
            raise Exception("Unable to get WebVTT file from S3, got exception : %s " % (e))

    # Read the MPD into a variable and convert from xml to Dict
    mpd_file = data_mpd['Body'].read()
    mpddoc = xmltodict.parse(mpd_file)

    # Create a list to track exceptions and exit if necessary
    manifest_exceptions = []

    if MANIFESTUPDATE == "True":

        ### All of the MPD Get details/delete actions below are inside TRY blocks
        ### Add or remove more Get details/delete/add actions inside individual TRY block
        ### Any exceptions will be caught and displayed in a DEBUG message. 
        ### Any exception deemed to great to recover from will exit the function
        ### An exception does not cause the workflow to fail

        LOGGER.info("Manifest Modifier: Starting...")

        ### Get details at the MPD Level Here ### START
        # EXAMPLE : mpddoc['MPD']['@attribute'] == XX


        mpd_header = dict(mpddoc['MPD'])
        mpd_header['@xmlns:scte35'] = "urn:scte:scte35:2013:xml"
        del mpd_header['Period']

        ### Get details at the MPD Level Here ### END

        adaptation_sets = dict()
        representations_d = dict()

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

            ### Get details at the Period Level Here ### START
            ## p['attribute']


            ### Get details at the Period Level Here ### END

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

                adapt_reps = []
                a_dict = dict(a)
                del a_dict['Representation']
                ### Get details at the AdaptationSet Level Here ### START
                ## a['attribute']


                if a['@mimeType'] == "audio/mp4": # this is audio
                    try:
                        adaptation_set_type = "audio!" + a['Label']
                        if adaptation_set_type not in adaptation_sets:
                            adaptation_sets[adaptation_set_type] = a_dict
                            adaptation_sets[adaptation_set_type]['representations'] = ""
                    except:
                        raise Exception("Audio Adaptation Sets must be labeled.")

                elif a['@mimeType'] == "video/mp4": # assume video
                    adaptation_set_type = a['@mimeType']
                    if adaptation_set_type not in adaptation_sets:
                        adaptation_sets[adaptation_set_type] = a_dict
                        adaptation_sets[adaptation_set_type]['representations'] = ""
                #

                #adapt_reps.append(r['@id'])
                #adaptation_sets[adaptation_set_type]['representations'] = adapt_reps

                ### Get details at the AdaptationSet Level Here ### END


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

                    rep_id = str(r['@id'])
                    rep_details = dict(r)

                    ### Get details at the Representation Level Here ### START
                    ## r['attribute']
                    if isinstance(r['SegmentTemplate']['SegmentTimeline']['S'],list):
                        timeline = len(r['SegmentTemplate']['SegmentTimeline']['S'])
                        LOGGER.debug("Manifest Modifier: Representation %s has multiple segments in timeline" % (r))
                        t_layout = "m"
                    else:
                        timeline = 1
                        LOGGER.debug("Manifest Modifier: Representation %s has single segment timeline element in timeline" % (r))
                        t_layout = "s"

                    adapt_reps.append(rep_id)

                    rep_segments = []
                    rep_segments.clear()
                    for segmenttime in range(0,timeline):
                        if t_layout == "s":
                            t = r['SegmentTemplate']['SegmentTimeline']['S']
                        else:
                            t = r['SegmentTemplate']['SegmentTimeline']['S'][segmenttime]

                        segtime = t['@t']
                        segdur = t['@d']
                        rep_segments.append({"@t":segtime,"@d":segdur})

                        if "@r" in t: # repetitive segments

                            for reprange in range(1,int(t['@r'])+1):
                                reptime = int(reprange) * int(segdur) + int(segtime)
                                rep_segments.append({"@t":reptime,"@d":segdur})


                    del r['SegmentTemplate']['SegmentTimeline']
                    if rep_id not in representations_d:
                        representations_d[rep_id] = r

                    if "segments" in representations_d[rep_id]:
                        merge_segments = representations_d[rep_id]['segments'] + rep_segments
                        representations_d[rep_id]['segments'] = merge_segments
                    else:
                        representations_d[rep_id]['segments'] = rep_segments

                adaptation_sets[adaptation_set_type]['representations'] = adapt_reps
        # get the video timescale to calculate duration
        try:
            video_timescale = adaptation_sets[list(adaptation_sets.keys())[0]]['SegmentTemplate']['@timescale']
        except Exception as e:
            LOGGER.error("Unable to get timescale from adaptation set, got exception %s " % (e))
            manifest_exceptions("Unable to get timescale from adaptation set, got exception %s " % (e))
            raise Exception("Unable to get timescale from adaptation set, got exception %s " % (e))

        # Asset Duration , calculated from last PTS stamp of representation id 1 + duration of that segment
        duration_pts = int(representations_d['1']['segments'][-1]['@t']) + int(representations_d['1']['segments'][-1]['@d'])
        duration_presentation_m = int((duration_pts / int(video_timescale)) / 60)
        duration_presentation_s = round((duration_pts / int(video_timescale)) - (duration_presentation_m * 60),3)
        duration_presentation = "PT"+str(duration_presentation_m)+"M"+str(duration_presentation_s)+"S"


        if VTTPRESENT:
            ### VTT Segment creation start
            vtt_representation_id = '/'.join(vtt_full_no_ext.rsplit("/",3)[-2:])

            # Create VTT Representation and add to dict
            vtt_representation = str(len(representations_d) + 1)
            representations_d[vtt_representation] = copy.deepcopy(representations_d[list(representations_d.keys())[0]])
            representations_d[vtt_representation] = {}
            representations_d[vtt_representation]['@id'] = vtt_representation_id #Path to vtt base /vtt/fullvtt
            representations_d[vtt_representation]['@bandwidth'] = "52"
            representations_d[vtt_representation]['SegmentTemplate'] = {}
            representations_d[vtt_representation]['SegmentTemplate']['@timescale'] = video_timescale
            representations_d[vtt_representation]['SegmentTemplate']['@media'] = "$RepresentationID$_$Number$.vtt"
            representations_d[vtt_representation]['segments'] = copy.deepcopy(representations_d[list(representations_d.keys())[0]]['segments'])

            # Create VTT Adaptation Set
            vtt_dict = dict()
            vtt_dict['text/vtt'] = {}
            vtt_dict['text/vtt']['@mimeType'] = "text/vtt"
            vtt_dict['text/vtt']['@lang'] = "en"
            vtt_dict['text/vtt']['SegmentTemplate'] = {}
            vtt_dict['text/vtt']['SegmentTemplate']['@timescale'] = video_timescale
            vtt_dict['text/vtt']['representations'] = [vtt_representation]

            # Add Adaptation Set to dict
            adaptation_sets.update(vtt_dict)

            # Create VTT segments from full vtt
            LOGGER.info("Starting VTT Segmenter process.. this may take a few minutes")
            vtt_segment_number = 1
            for segment in representations_d[vtt_representation]['segments']:
                new_vtt = []
                new_vtt.clear()
                vtt_start = float(float(segment['@t']) / float(video_timescale))
                vtt_end = float(vtt_start + float(segment['@d']) / float(video_timescale))

                lines_to_delete = []
                for line in range(1,len(vtt_list)):
                    if not vtt_list[line][0:2].isdigit():
                        # this line is malformed or should be a part of the previous line
                        vtt_list[line-1] = vtt_list[line-1] + "\n" + vtt_list[line]
                        lines_to_delete.append(int(line))

                lines_to_delete.sort(reverse = True )
                for ltd in lines_to_delete:
                    #return ltd
                    vtt_list.pop(ltd)

                new_vtt.append(vtt_list[0] + "\n\n")
                for line_number in range(1,len(vtt_list)):
                    if len(vtt_list[line_number]) < 20:
                        LOGGER.info("VTT Line number %s has no good VTT Data, malformed or empty" % (line_number) )
                    else:
                        start_time_str = vtt_list[line_number].split("-->")[0].replace(" ","") # "00:00:01.042"
                        end_time_str = vtt_list[line_number].split("-->")[1].split(" ")[1].split("\n")[0]

                        start_time_seconds = (int(start_time_str.split(":")[0]) * 3600) + (int(start_time_str.split(":")[1]) * 60) + float(start_time_str.split(":")[2])
                        end_time_seconds = (int(end_time_str.split(":")[0]) * 3600) + (int(end_time_str.split(":")[1]) * 60) + float(end_time_str.split(":")[2])

                        if start_time_seconds >= vtt_start and start_time_seconds < vtt_end:
                            new_start_time_seconds = datetime.timedelta(seconds = start_time_seconds - vtt_start)
                            new_end_time_seconds = datetime.timedelta(seconds = end_time_seconds - vtt_start)
                            new_start_time = str("0") + str(new_start_time_seconds)[:-3]
                            new_end_time = str("0") + str(new_end_time_seconds)[:-3]
                            new_start_time = start_time_str
                            new_end_time = end_time_str

                            new_vtt.append(vtt_list[line_number].replace("â\u0099ª","♪").replace(start_time_str,new_start_time).replace(end_time_str,new_end_time) + "\n\n") ## the string replace is because the 'music note' gets malformed during the vtt response decode

                vtt_str = ""
                for line in new_vtt:
                    vtt_str = vtt_str + line

                # bucket is known
                # key is = original key + _ + segment_number + .vtt
                new_vtt_key = "%s_%s.vtt" % (vtt_full_no_ext.split("/",3)[-1],vtt_segment_number)
                try:
                    s3_put_response = s3.put_object(Body=vtt_str, Bucket=bucket, Key=new_vtt_key, ACL='public-read')
                except Exception as e:
                    manifest_exceptions.append("Unable to write new VTT File to S3, got exception : %s " % (e))

                vtt_segment_number += 1

        ### VTT Segment creation end

        LOGGER.info("Parsed manifest completely, now going to make a single period manifest with %s EventStream Elements" % (str(len(esam_break_points))))
        LOGGER.info("NPT Points are at : %s " % (esam_break_points))

        period_timing = dict()
        period_number = 1
        period_timing[str(period_number)] = 0,duration_pts

        ## Create EventStream Elements
        eventstream = []



        scte_type = [52,53]
        for break_point in range(0,len(esam_break_points_duration)):
            for s_type in scte_type:
                break_info = esam_break_points_duration[break_point]
                pts_time = int(float(break_info[0]) * float(video_timescale))
                duration = int(float(break_info[1]) * float(video_timescale))
                event_id = str(break_point)


                LOGGER.debug("EventStream PTS time %s " % (str(pts_time)))

                scte_event = dict()
                scte_event['@timescale'] = video_timescale
                scte_event['@duration'] = str(duration)
                scte_event['@presentationTime'] = str(pts_time)
                scte_event['scte35:SpliceInfoSection'] = {}
                scte_event['scte35:SpliceInfoSection']['@protocolVersion'] = "0"
                scte_event['scte35:SpliceInfoSection']['@tier'] = "4095"
                scte_event['scte35:SpliceInfoSection']['scte35:TimeSignal'] = {}
                scte_event['scte35:SpliceInfoSection']['scte35:TimeSignal']['scte35:SpliceTime'] = {}
                scte_event['scte35:SpliceInfoSection']['scte35:TimeSignal']['scte35:SpliceTime']['@ptsTime'] = str(pts_time)
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor'] = {}
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@segmentationEventId'] = event_id
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@segmentationEventCancelIndicator'] = "false"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['@segmentationDuration'] = str(duration)
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions'] = {}
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@webDeliveryAllowedFlag'] = "false"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@noRegionalBlackoutFlag'] = "false"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@archiveAllowedFlag'] = "true"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:DeliveryRestrictions']['@deviceRestrictions'] = "3"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid'] = {}
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentationUpidType'] = "12"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentationUpidLength'] = "0"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentationTypeId'] = str(s_type)
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentNum'] = "0"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:SegmentationUpid']['@segmentsExpected'] = "1"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:BreakDuration'] = {}
                #scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:BreakDuration']['@autoReturn'] = "true"
                scte_event['scte35:SpliceInfoSection']['scte35:SegmentationDescriptor']['scte35:BreakDuration']['@duration'] = str(duration)

                eventstream.append(scte_event)


        # Start building new MPD
        new_mpd_period_layout = []
        p_representations = dict()
        p_adaptation_sets = dict()

        for new_mpd_period in period_timing:
            # create dictionary copies
            p_representations = copy.deepcopy(representations_d)
            p_adaptation_sets = copy.deepcopy(adaptation_sets)


            period_start = period_timing[new_mpd_period][0]
            period_end = period_timing[new_mpd_period][1]
            representation_index = dict()
            representation_collapse = dict()

            LOGGER.info("New Manifest Period %s has duration %s PTS" % (str(period_start),str(period_end)))

            period_duration = dict()
            for r in p_representations:
                representation_index[str(r)] = []
                segment_number = 1
                start_index = []
                period_duration_pts = 0

                # get timescale
                factor = 0
                for a in p_adaptation_sets:
                    if r in p_adaptation_sets[a]['representations']:
                        factor = float(p_adaptation_sets[a]['SegmentTemplate']['@timescale'])

                if factor == 0:
                    manifest_exceptions.append("Unable to get timescale from the adaptation set of representation %s" % (str(r)))

                for s in p_representations[r]['segments']:

                    if float(s['@t']) / factor >= float(period_start) - 0.33 and float(int(s['@t']) / factor) < period_end - 0.33:
                        representation_index[str(r)].append(s)
                        start_index.append(segment_number)
                        period_duration_pts += int(s['@d'])
                    segment_number += 1

                period_duration_presentation_m = int((period_duration_pts / factor) / 60)
                period_duration_presentation_s = round((period_duration_pts / factor) - (period_duration_presentation_m * 60),3)
                period_duration_presentation = "PT"+str(period_duration_presentation_m)+"M"+str(period_duration_presentation_s)+"S"
                period_duration[r] = period_duration_presentation

                # representation_index[r] should have all segments in timeline listed explicitly. now we can compress with @r attributes
                segment_count = 0
                repeat_timeline = []

                while segment_count < len(representation_index[str(r)]):

                    repeat_counter = 0
                    segment_timeline = copy.deepcopy(representation_index[str(r)][segment_count])

                    #if segment_count < len(representation_index[r]):

                    repeat_true = "true"
                    while repeat_true == "true" and segment_count + 1 < len(representation_index[str(r)]):

                        if segment_count + 1 < len(representation_index[r]):

                            if representation_index[str(r)][segment_count+1]['@d'] is representation_index[str(r)][segment_count]['@d']:

                                repeat_counter += 1
                                segment_count += 1
                            else:
                                repeat_true = "false"

                    if repeat_counter > 0:
                        segment_timeline.update({"@r":repeat_counter})
                        #segment_timeline.update({"@t":segment_timeline['@t'],"@d":segment_timeline['@d'], "@r":repeat_counter})
                    repeat_timeline.append(segment_timeline)
                    segment_count += 1
                representation_collapse[r] = repeat_timeline

                representation_index['startNumber_'+str(r)] = start_index[0]
                representation_index['periodDuration_'+str(new_mpd_period)] = period_duration_presentation

            for a in p_adaptation_sets:

                adaptation_representation = []
                for r in p_adaptation_sets[a]['representations']:

                    representation_header = dict(p_representations[r])

                    del representation_header['segments']
                    representation_header['SegmentTemplate'].update(p_adaptation_sets[a]['SegmentTemplate'])
                    representation_header['SegmentTemplate']['SegmentTimeline'] = {}
                    representation_header['SegmentTemplate']['SegmentTimeline']['S'] = representation_collapse[r] # representation_collapse will have 'r' attributes in segment timelines

                    representation_header['SegmentTemplate']['@startNumber'] = str(representation_index['startNumber_'+r])

                    adaptation_representation.append(representation_header)

                    representation_header['SegmentTemplate']['@presentationTimeOffset'] = adaptation_representation[0]['SegmentTemplate']['SegmentTimeline']['S'][0]['@t']

                p_adaptation_sets[a]['@segmentAlignment'] = "true"
                del p_adaptation_sets[a]['representations']
                del p_adaptation_sets[a]['SegmentTemplate']
                p_adaptation_sets[a]['Representation'] = adaptation_representation

            new_ad_sets = []

            for a in p_adaptation_sets:
                new_ad_sets.append(p_adaptation_sets[a])

            new_mpd_period_layout.append({"@start":"PT0.00S","@duration":period_duration["1"], "@id":new_mpd_period, "EventStream":{"@timescale":video_timescale,"@schemeIdUri":"urn:scte:scte35:2013:xml", "Event":eventstream}, "AdaptationSet":new_ad_sets})
            #new_mpd_period_layout.append({"@duration":period_duration["1"], "@id":new_mpd_period, "AdaptationSet":new_ad_sets})


        new_mpd = dict()
        new_mpd['MPD'] = mpd_header
        new_mpd['MPD']['Period'] = new_mpd_period_layout

        #return new_mpd
        new_mpd_xml = xmltodict.unparse(new_mpd, short_empty_elements=True, pretty=True).encode('utf-8')

        LOGGER.info("Manifest Modifier: Complete...")
        LOGGER.info("Manifest Modifier: Exceptions during Get details : %s " % (str(len(manifest_exceptions))))
        LOGGER.debug("Manifest Modifier - Exceptions caught : %s " % (manifest_exceptions))

        LOGGER.debug("New MPD : %s" % (new_mpd_xml))

        try:
            s3_put_response = s3.put_object(Body=new_mpd_xml, Bucket=bucket, Key=new_key, ACL='public-read')
        except Exception as e:
            raise Exception("Unable to write new manifest to S3, got exception : %s " % (e))
        return s3_put_response
    else:
        raise Exception("Not doing anything")