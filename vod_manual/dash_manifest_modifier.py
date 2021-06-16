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

import os
import sys
import json
import logging
import xmltodict

#logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
#LOGGER = logging.getLogger()

# Create Logging Handler
LOGGER = logging.getLogger('MPEG2 DASH Modifier')
LOGGER.setLevel(logging.INFO)

# Create File Handler For Logging
#fh = logging.FileHandler('mpeg2-corrector.log') ## Un-comment this line when doing console testing
#fh.setLevel(logging.DEBUG) ## Un-comment this line when doing console testing

# Create Console Handler
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#fh.setFormatter(formatter) #### Un-comment this line when doing console testing
ch.setFormatter(formatter)

# add the handlers to the logger
#LOGGER.addHandler(fh) #### Un-comment this line when doing console testing
LOGGER.addHandler(ch)

if __name__ == '__main__':

    LOGGER.info("Starting DASH Manifest Modifier script")
    server_args = json.loads(sys.argv[1])
    LOGGER.debug("Elemental Server Output : %s " % (str(server_args)))
    LOGGER.info(server_args['output_groups'][0]['outputs'][0]['output_path'])


    dash_mpd_path = server_args['output_groups'][0]['outputs'][0]['output_path']

    try:
        cat_command = 'cat %s' % (dash_mpd_path)
        cat_stream = os.popen(cat_command)
        mpeg_dash_xml = str(cat_stream.read())
    except Exception as e:
        raise Exception("ERROR reading Manifest, got exception : %s " % (e))

    # Use XMLToDict to convert XML to json
    mpddoc = xmltodict.parse(mpeg_dash_xml)

    ##
    ## DASH modifying section
    ##

    ### All of the MPD modify/delete actions below are inside TRY blocks
    ### Add or remove more modify/delete/add actions inside individual TRY block
    ### Any exceptions will be caught and displayed in a DEBUG message. 
    ### An exception does not cause the workflow to fail
   
    manifest_modify_exceptions = [] 
    LOGGER.info("Manifest Modifier: Starting...")
        
    ### Modify at the MPD Level Here ### START
    # EXAMPLE : mpddoc['MPD']['@attribute'] == XX
        
    try:
        mpddoc['MPD']['@profiles'] = "urn:mpeg:dash:profile:isoff-live:2011"
    except Exception as e:
        manifest_modify_exceptions.append("Can't change profile attribute value : %s" % (e))
        
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
        try:
            del p['@start']
        except Exception as e:
            manifest_modify_exceptions.append("Period %s : Unable to remove start attribute : %s" % (period,e))
        try:
            del p['EventStream']
        except Exception as e:
            manifest_modify_exceptions.append("Period %s : Unable to remove EventStream element : %s" % (period,e))
        
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
                
            ### Modify at the AdaptationSet Level Here ### START
            ## a['attribute']
            try:
                a['@segmentAlignment'] = "true"
            except Exception as e:
                manifest_modify_exceptions.append("Period %s - AdaptationSet %s : Unable to change segmentAlignment value : %s" % (period,adaptationset,e))
        
        
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

        LOGGER.info("Manifest Modifier: Complete...")
        LOGGER.info("Manifest Modifier: Exceptions during modify : %s " % (str(len(manifest_modify_exceptions))))
        LOGGER.debug("Manifest Modifier - Exceptions caught : %s " % (manifest_modify_exceptions))
    
        new_mpd = xmltodict.unparse(mpddoc, short_empty_elements=True, pretty=True)


    ##
    ## DASH modifying section - end
    ##


    ##
    ##  Write New DASH Manifest to previous one
    ##
    dash_mpd_path = dash_mpd_path + "-new.mpd"
    f = open( dash_mpd_path, 'w+' )
    f.write( str(new_mpd) )
    f.close() 
