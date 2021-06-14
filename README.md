# DASH Manifest Modifier
## Overview
This code is designed to modify the contents of an MPEG DASH manifest as part of a LIVE PROXY workflow, or as an offline/static manifest rewrite. The purpose of the code is to get the DASH manifest (produced by a transcoder or packager) to conform to the requirements of downstream components or players.

## Variations
There are multiple versions of the code, based on whether the DASH package is LIVE or VOD, and how the script is to be triggered:

* [VOD : Post-transcode script (Transcoder : Elemental Server)](vod_post_transcode/README-VOD-POSTTX.md)
* VOD : Post-transcode script (Transcoder : AWS Elemental MediaConvert), triggered via CloudWatch event
* VOD : User input NFS path (manual entry : `$ python dash_manifest_modifier.py /data/server/output/asset_1/index.mpd`)
* LIVE : Proxy triggered by client HTTPS request (Proxy: Amazon API Gateway & AWS Lambda)
