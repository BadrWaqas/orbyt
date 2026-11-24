# Data licences and attribution

The MIT licence in this repo covers the code only. Each data source keeps its own terms. This list follows PLAN.md section 7.3 and covers every source named there, including the ones not in use yet. Last reviewed 24 November 2026.

The site shows the credits for the sources in use in the footer of every page, and the map shows the OpenStreetMap, OpenFreeMap and OpenMapTiles credit on the map itself.

## Sources in use

| Source | Used for | Terms and attribution | In use since |
|---|---|---|---|
| Copernicus Sentinel-5P | NO2 columns | Free and open. Credit "Contains modified Copernicus Sentinel data [year]". | M1 |
| ERA5 (Copernicus Climate Change Service) | Wind | Credit "Contains modified Copernicus Climate Change Service information [year]", and state that neither the European Commission nor ECMWF is responsible for any use made of the information. Terms: the Licence to use Copernicus Products. | M3 |
| EEA Industrial Reporting database | Reported NOx, EU | Reuse with attribution to the European Environment Agency. The EEA publishes data derived from reported data under CC BY. The exact wording on the dataset page has not been confirmed word for word, so check it before launch. | M1 |
| EPA CAMPD hourly emissions | Validation, US | US government data, credit the US EPA Clean Air Markets Division. Read from the PUDL republication (release v2026.11.0, Catalyst Cooperative, CC BY 4.0), which needs no API key. Credit PUDL as well. | M4 |
| EPA National Emissions Inventory 2023, facility summary | Validation, US: NOx the stack monitors do not cover | US government data, credit the US EPA. | M4.4 |
| OpenFreeMap vector tiles | Basemap | Free public tiles. Show the OpenFreeMap, OpenMapTiles and "OpenStreetMap contributors" credit on the map. | M0 |
| OpenStreetMap | Basemap data | ODbL. Show "OpenStreetMap contributors". | M0 |
| NASA Black Marble (VIIRS night lights, 2016 composite) via NASA GIBS | Night lights under the globe at low zoom | Free and open. NASA asks for an acknowledgement: credit NASA Earth Observatory images by Joshua Stevens, using Suomi NPP VIIRS data from Miguel Roman, NASA GSFC, and acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS). Shown in the map's credits, the footer and the About page. Self-hosted copy of zoom 0 to 5, recoloured onto the site's palette. | M7.2 |

## Sources named in the plan, not in use yet

| Source | Planned use | Terms and what to do | Status |
|---|---|---|---|
| Beirle et al. NOx point source catalogue v2 | Early demo | CC BY 4.0. Cite the paper. | Planned, M2 |
| Climate TRACE | Reported and modelled emissions for comparison | CC BY 4.0. Cite Climate TRACE. | Not used |
| Sentinel-2 cloudless by EOX | Satellite image base layer | Only the 2016 edition is CC BY 4.0. Later editions are non-commercial and must not be used here. If used, credit "Sentinel-2 cloudless, s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016)". | Not used |
| Carbon Mapper | Methane plume data | Non-commercial and share-alike. Display with attribution, do not rehost bulk data, and do not mix it into the MIT-licensed downloads. | Not used |
| IMEO Eye on Methane | Methane data | Open. Read and follow the terms of use on the day it is added. | Not used |

## Rules for adding a source

1. Read the source's own terms before the first download, and add a row here in the same commit that adds the source.
2. Put the credit it asks for in the footer list in `web/src/app/credits.ts`.
3. Anything with a non-commercial or share-alike term stays out of the files under `web/public/data/` and out of the downloads on the Data page.
