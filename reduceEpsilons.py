#!/usr/bin/python3

# reduceEpsilons.py
#
# This module takes the inputs used by createBetaMap.py as well as the epsilon
# file to prepare. 
import csv
import os
import sys
import yaml

# Import our libraries
sys.path.append(os.path.join(os.path.dirname(__file__), "include"))

from include.ascFile import load_asc
from include.calibrationLib import get_bin, load_betas, load_configuration, get_climate_zones, get_treatments_raster
from include.utility import *

# TODO Figure out a better way to store these locations, maybe a library that finds them?
# Country specific inputs
CALIBRATION = "data/calibration.csv"
POPULATION_FILE = "rwa_population.asc"

# TODO RWA has only a single treatment rate and ecozone
TREATMENT = 0.99
ECOZONE = 0

# These are generated by createBetaMap, so should be present
# TODO Add these as command line inputs, or parameters
BETAVALUES = "out/mean_beta.asc"
EPSILONVALUES = "out/epsilons_beta.asc"

# Default output
RESULTS = "out/reduction.csv"
SCRIPT = "out/script.sh"

parameters = {}


def addBeta(lookup, step, zone, beta, population, treatment):
    global parameters
    
    # Determine the population and treatment bin we are working with
    populationBin = int(get_bin(population, lookup[zone].keys()))
    treatmentBin = get_bin(treatment, lookup[zone][populationBin].keys())

    # Update the dictionary
    if zone not in parameters:
        parameters[zone] = {}
    if populationBin not in parameters[zone]:
        parameters[zone][populationBin] = {}
    if treatmentBin not in parameters[zone][populationBin]:
        parameters[zone][populationBin][treatmentBin] = set()

    # Add the stepped betas to the set
    value = round(beta - (step * 10), 4)
    while value < beta + (step * 10):
        # Only add values greater than zero
        if value > 0:
            parameters[zone][populationBin][treatmentBin].add(value)
        value = round(value + step, 4)
  

def getLookupBetas(lookup, zone, population, treatment):
    betas = set()
    for row in lookup[zone][population][treatment]:
        betas.add(row[1])
    return betas


def writeBetas(lookup, username):
    global parameters

    # Generate a list of populations to create ASC files for
    populationAsc = set()

    # Generate a list of betas to run (same format as missing.csv) that haven't been seen before
    reduced = []
    for zone in sorted(parameters.keys()):
        for population in sorted(parameters[zone].keys()):
            populationAsc.add(population)
            for treatment in sorted(parameters[zone][population]):
                betas = getLookupBetas(lookup, zone, population, treatment)
                for beta in sorted(parameters[zone][population][treatment]):
                    if beta not in betas:
                        reduced.append([zone, population, treatment, beta])

    # Double check to see if the list was cleared out
    if len(reduced) == 0:
        print("Nothing to reduce!")
        return

    # Save the missing values as a CSV file
    print("Preparing inputs, {}".format(RESULTS))
    with open(RESULTS, "w") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(reduced)

    print("Preparing script, {}".format(SCRIPT))
    with open(SCRIPT, "w") as script:
        script.write("#!/bin/bash\n")
        script.write("source ./calibrationLib.sh\n")
        value = " ".join([str(x) for x in sorted(populationAsc)])
        script.write("generateAsc \"\\\"{}\\\"\"\n".format(value.strip()))
        value = " ".join([str(x) for x in sorted(parameters.keys())])
        script.write("generateZoneAsc \"\\\"{}\\\"\"\n".format(value.strip()))
        script.write("runCsv '{}' {}\n".format(RESULTS[4:], username))
        

def main(configuration, gisPath, tolerance, step, username):
    global parameters

    # Load the configuration, and potentially raster data
    cfg = load_configuration(configuration)
    climate = get_climate_zones(cfg, gisPath)
    treatment = get_treatments_raster(cfg, gisPath)

    # Load the relevent raster data
    filename = os.path.join(gisPath, POPULATION_FILE)    
    [ascheader, population] = load_asc(filename)
    lookup = load_betas(CALIBRATION)

    # Read the epsilons file in
    [_, beta] = load_asc(BETAVALUES )
    [_, epsilon] = load_asc(EPSILONVALUES)

    print ("Evaluating epsilons for {} rows, {} columns".format(ascheader['nrows'], ascheader['ncols']))

    # Scan each of the epsilons
    for row in range(0, ascheader['nrows']):
        for col in range(0, ascheader['ncols']):
            # Pass on nodata
            value = epsilon[row][col]
            if value == ascheader['nodata']: continue

            # Pass when value is less than maximum
            if value < tolerance: continue

            # Update the running list
            addBeta(lookup, step, climate[row][col], beta[row][col], population[row][col], treatment[row][col])

        # Note the progress
        progressBar(row + 1, ascheader['nrows'])

    # Check to see if we are done
    if len(parameters) == 0:
        print("Nothing to reduce!")
    else:
        writeBetas(lookup, username)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: ./reduceEpsilons.py [configuration] [GIS] [tolerance] [step] [username]")
        print("configuration - the configuration file to be loaded")
        print("gis - the directory that GIS files can be found in")        
        print("tolerance - float, maximum epsilon")
        print("step - float, increment +/- 10x around known beta (maximum 0.00001)")
        print("username - the user who will be running the calibration on the cluster")
        exit(0)
                
    # Parse the parameters
    configuration = sys.argv[1]
    gisPath = str(sys.argv[2])
    tolerance = float(sys.argv[3])
    step = float(sys.argv[4])
    username = str(sys.argv[5])

    # Step cannot be greater than one
    if step >= 1:
        print("The step cannot be greater than one")
        exit(1)

    # Can only go out to five decimal places
    if round(step, 5) != step:
        print("{} exceeds maximum step of 0.00001".format(step))
        exit(1)

    main(configuration, gisPath, tolerance, step, username)