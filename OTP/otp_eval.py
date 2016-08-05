'''
Created on Mar 16, 2016

Batch processing of routes in OpenTripPlanner
to be used with Jython (Java Bindings!)

@author: Christoph Franke
'''
#!/usr/bin/jython

from org.opentripplanner.scripting.api import OtpsEntryPoint, OtpsCsvOutput
from org.opentripplanner.routing.core import TraverseMode
from org.opentripplanner.scripting.api import OtpsResultSet, OtpsAggregate
from config import (GRAPH_PATH, LONGITUDE_COLUMN, LATITUDE_COLUMN, 
                    ID_COLUMN, DATETIME_FORMAT, AGGREGATION_MODES,
                    ACCUMULATION_MODES)
from datetime import datetime
import sys


class OTPEvaluation(object):
    '''
    Use to calculate the reachability between origins and destinations with OpenTripPlanner
    and to save the results to a csv file
    
    Parameters
    ----------
    router: name of the router to use for trip planning
    print_every_n_lines: optional, determines how often progress in processing origins/destination is written to stdout (default: 50)
    calculate_details: optional, if True, evaluates additional informations about itineraries (a little slower)
    '''   
    def __init__(self, router, print_every_n_lines=50, calculate_details=False, smart_search=False):
        self.otp = OtpsEntryPoint.fromArgs([ "--graphs", GRAPH_PATH, "--router", router])
        self.router = self.otp.getRouter()
        self.request = self.otp.createRequest()
        # smart search needs details (esp. start/arrival times), 
        # even if not wanted explicitly
        if smart_search:
            calculate_details = True
        self.calculate_details = calculate_details
        self.smart_search = smart_search     
        self.arrive_by = False   
        self.print_every_n_lines = print_every_n_lines
    
    def setup(self, 
              date_time=None, max_time=None, max_walk=None, walk_speed=None, 
              bike_speed=None, clamp_wait=None, banned='', modes=None, 
              arrive_by=False, max_transfers=None, max_pre_transit_time=None,
              wheel_chair_accessible=False, max_slope=None):
        '''
        sets up the routing request
        
        Parameters
        ----------
        date_time: optional, datetime object, start respectively arrival time (if arriveby == True)
        modes: optional, string with comma-seperated traverse-modes to use
        banned: optional, string with comma-separated route specs, each of the format[agencyId]_[routeName]_[routeId]  
        arrive_by: optional, if True, given time is arrival time (reverts search tree)
        max_walk: optional, maximum distance (in meters) the user is willing to walk 
        walk_speed: optional, walking speed in m/s
        bike_speed: optional, bike speed in m/s
        clamp_wait: optional, maximum wait time in seconds the user is willing to delay trip start (-1 seems to mean it will be ignored)
        max_transfers: optional, maximum number of transfers (= boardings - 1)
        max_pre_transit_time: optional, maximum time in seconds of pre-transit travel when using drive-to-transit (park andride or kiss and ride)
        wheel_chair_accessible: optional, if True, the trip must be wheelchair accessible (defaults to False)
        max_slope: optional, maximum slope of streets for wheelchair trips
        '''
        
        if date_time is not None:
            self.request.setDateTime(date_time.year, date_time.month, date_time.day, date_time.hour, date_time.minute, date_time.second) 
        
        self.request.setArriveBy(arrive_by)
        self.arrive_by = arrive_by
        self.request.setWheelChairAccessible(wheel_chair_accessible)
        if max_walk is not None:
            self.request.setMaxWalkDistance(max_walk)
        if walk_speed is not None:
            self.request.setWalkSpeedMs(walk_speed)
        if bike_speed is not None:
            self.request.setBikeSpeedMs(bike_speed)
        if clamp_wait is not None:
            self.request.setClampInitialWait(clamp_wait)
        if banned:
            self.request.setBannedRoutes(banned)
        if max_slope is not None:
            self.request.setMaxSlope(max_slope)
        if max_transfers is not None:
            self.request.setMaxTransfers(max_transfers)
        if max_pre_transit_time is not None:
            self.request.setMaxPreTransitTime(max_pre_transit_time)
             
        if modes:          
            self.request.setModes(modes)
            
    def evaluate(self, times, max_time, origins_csv, destinations_csv, do_merge=False):
        '''
        evaluate the shortest paths between origins and destinations
        uses the routing options set in setup() (run it first!)
        
        Parameters
        ----------
        times: list of date times, the desired start/arrival times for evaluation
        origins_csv: file with origin points
        destinations_csv: file with destination points
        do_merge: merge the results over time, only keeping the best connections    
        max_time: maximum travel-time in seconds (the smaller this value, the smaller the shortest path tree, that has to be created; saves processing time)
        '''                   
    
        origins = self.otp.loadCSVPopulation(origins_csv, LATITUDE_COLUMN, LONGITUDE_COLUMN)    
        destinations = self.otp.loadCSVPopulation(destinations_csv, LATITUDE_COLUMN, LONGITUDE_COLUMN)   
        
        # next start/arrival time detected (of ALL results)   
        min_next_time = None 

        if self.arrive_by:
            time_note = 'arrival time '
            min_next_times = [sys.maxint] * destinations.size()
            #time_table = [[None] * len(orgins)] * len(destinations)
        else:
            time_note = 'start time ' 
            min_next_times = [sys.maxint] * origins.size()
            #time_table = [[None] * len(destinations)] * len(origins)
            
        results = []
        # iterate all times
        for date_time in times:    
            # compare seconds since epoch (different ways to get it from java/python date)
            epoch = datetime.utcfromtimestamp(0)
            time_since_epoch = (date_time - epoch).total_seconds()
            self.request.setDateTime(date_time.year, date_time.month, date_time.day, date_time.hour, date_time.minute, date_time.second)            
            # has to be set every time after setting datetime (and also AFTER setting arriveby)
            self.request.setMaxTimeSec(max_time)
            msg = 'Starting evaluation of routes with ' + time_note + date_time.strftime(DATETIME_FORMAT)
            
            if self.smart_search and min_next_time is not None:
                # skip the whole time slice, if next detected time is not reached (as they are already detected)
                if time_since_epoch <= (min_next_time + 10) / 1000: # 10 seconds tolerance
                    print msg + ' - SKIPPED'
                    continue
                
            print msg
                          
            if self.arrive_by:
                if self.smart_search:
                    for i, destination in destinations:
                        #ignore destination, if already found routes arrive later anyway
                        destination.setIgnored(time_since_epoch <= min_next_times[i])
                results_dt = self._evaluate_arrival(origins, destinations)
                if self.smart_search:
                    for result in results_dt:
                        min_next_times[i] = result.getMinArrivalTime().getTime()
            else:
                if self.smart_search:
                    for i, origin in enumerate(origins):
                        #ignore origin, if already found routes start later anyway
                        ignore = time_since_epoch <= min_next_times[i]
                        origin.setIgnored(ignore)
                results_dt = self._evaluate_departures(origins, destinations)   
                if self.smart_search:
                    for result in results_dt:
                        min_next_times[i] = result.getMinStartTime().getTime()  
            
            # detect the next start/arrival time (lowest of all found times)
            if self.smart_search: 
                min_next_time = min_next_times[0]
                for i in range(1, len(min_next_times)):
                    if min_next_times[i] < min_next_time:
                        min_next_time = min_next_times[i] 
                        
            results.append(results_dt)    
    
        # merge the results
        if do_merge:
            merged_results = []
            for n_results_per_time in range(len(results[0])):
                merged_result = results[0][n_results_per_time]
                for n_times in range(1, len(results)):
                    res = results[n_times][n_results_per_time]
                    merged_result = merged_result.merge(res)
                merged_results.append(merged_result)
            results = merged_results
        else:            
            # flatten the results
            results = [r for res in results for r in res] 
            
        return results
        

    def _evaluate_departures(self, origins, destinations):     
        '''
        evaluate the shortest paths from origins to destinations
        uses the routing options set in setup() (run it first!)
        
        Parameters
        ----------
        origins: origin individuals
        destinations: destination individuals
        '''       
        
        origins_processed = -1 # in case no origins are processed (shouldn't happen though)     
        origins_skipped = 0        
        
        result_sets = []

        for origins_processed, origin in enumerate(origins):
            spt = None
            if not origin.isIgnored():
                # Set the origin of the request to this point and run a search
                self.request.setOrigin(origin)
                spt = self.router.plan(self.request)
            else:
                origins_skipped += 1
                
            result_set = None
            
            if spt is not None:
            
                result_set = destinations.createResultSet()
                spt.eval(result_set, self.calculate_details)   
                result_set.setSource(origin)
                
            result_sets.append(result_set)                                
                
            if not (origins_processed + 1) % self.print_every_n_lines:
                print "Processing: {} origins processed".format(origins_processed + 1)
                
        msg = "A total of {} origins processed".format(origins_processed + 1)
        if origins_skipped > 0:
            msg += ", {} origins skipped".format(origins_skipped)   
        print msg
        return result_sets
    
    def _evaluate_arrival(self, origins, destinations):   
        '''
        evaluate the shortest paths from destinations to origins (reverse search)
        uses the routing options set in setup() (run it first!), arriveby has to be set
        
        Parameters
        ----------
        origins: origin individuals
        destinations: destination individuals
        '''        
     
        i = -1       
        result_sets=[]
         
        for i, destination in enumerate(self.destinations):
            spt = None
            if not destination.isIgnored():
                # Set the destination of the request to this point and run a search
                self.request.setDestination(destination)
                spt = self.router.plan(self.request)            
             
            if spt is not None:
                result_set = origins.createResultSet()
                spt.eval(result_set, self.calculate_details)           
                result_set.setSource(destination) 
                result_sets.append(result_set)
             
            if not (i + 1) % self.print_every_n_lines:
                print "Processing: {} destinations processed".format(i+1)    
          
        print "A total of {} destinations processed".format(i+1)    
        return result_sets
        
    def results_to_csv(self, result_sets, target_csv, oid, did, mode=None, field=None, params=None, bestof=None, arrive_by=False):         
        '''
        write result sets to csv file, may aggregate/accumulate before writing results
        
        Parameters
        ----------
        result_sets: list of result_sets
        target_csv: filename of the file to write to
        oid: name of the field of the origin ids
        did: name of the field of the destination ids
        mode: optional, the aggregation or accumulation mode (see config.AGGREGATION_MODES resp. config.ACCUMULATION_MODES)
        field: optional, the field to aggregate/accumulate
        params: optional, params needed by the aggregation/accumulation mode (e.g. thresholds)
        '''   
        print 'post processing results...'
        
        header = [ 'origin id' ]
        do_aggregate = do_accumulate = False
        if not mode:
            header += [ 'destination id', 'travel time (sec)', 'boardings', 'walk/bike distance (m)', 'start time', 'arrival time', 'traverse modes', 'waiting time (sec)', 'elevation gained (m)', 'elevation lost (m)'] 
        elif mode in AGGREGATION_MODES.keys():
            header += [field + '-aggregated']   
            do_aggregate = True
        elif mode in ACCUMULATION_MODES.keys():
            header += [field + '-accumulated']
            do_accumulate = True       
        
        out_csv = self.otp.createCSVOutput()
        out_csv.setHeader(header)
        
        if do_accumulate:
            acc_result_set = self.origins.getEmptyResultSet()
            
        # used for sorting times, times not set will be treated as max values
        def sorter(a):
            if a[1] is None:
                return sys.maxint
            return a[1]
        
        for result_set in result_sets: 
                
            if do_accumulate:
                if acc_result_set is None:
                    acc_result_set = result_set
                else:
                    result_set.setAccumulationMode(mode)
                    result_set.accumulate(acc_result_set, field, params)
                continue
                    
            times = result_set.getTimes()
            
            if arrive_by:
                dest_id = result_set.getSource().getStringData(did)          
                dest_ids = [dest_id for x in range(len(times))]      
                origin_ids = result_set.getStringData(oid)     
            else:
                origin_id = result_set.getSource().getStringData(oid)          
                origin_ids = [origin_id for x in range(len(times))]  
                dest_ids = result_set.getStringData(did)     
             
            if do_aggregate:
                result_set.setAggregationMode(mode)
                aggregated = result_set.aggregate(field, params)
                out_csv.addRow([origin_id, aggregated])  
            
            else:            
                boardings = result_set.getBoardings()
                walk_distances = result_set.getWalkDistances()
                starts = result_set.getSampledStartTimes()
                timesToItineraries = result_set.getTimesToItineraries()
                arrivals = result_set.getArrivalTimes()     
                modes = result_set.getTraverseModes()
                waiting_times = result_set.getWaitingTimes()
                elevationGained = result_set.getElevationGained()
                elevationLost = result_set.getElevationLost()
                
                if bestof is not None:
                    indices = [t[0] for t in sorted(enumerate(times), key=sorter)]
                    indices = indices[:bestof]
                else:
                    indices = range(len(times))
                for j in indices:
                    time = times[j]
                    if time is not None:
                        out_csv.addRow([origin_ids[j], 
                                        dest_ids[j], 
                                        times[j], 
                                        boardings[j], 
                                        walk_distances[j],
                                        starts[j], 
                                        arrivals[j], 
                                        modes[j], 
                                        waiting_times[j], 
                                        elevationGained[j], 
                                        elevationLost[j]])
    
        if do_accumulate:
            results = acc_result_set.getResults()
            origin_ids = acc_result_set.getStringData(oid)   
            for i, res in enumerate(results):
                out_csv.addRow([origin_ids[i], res])
            
        out_csv.save(target_csv)
        print 'results written to "{}"'.format(target_csv)  
            