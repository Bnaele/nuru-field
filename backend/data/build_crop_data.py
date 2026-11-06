"""Build backend/data/crop_reference.csv from the FAO ECOCROP archive.

Why this exists
---------------
The hackathon build shipped a hand-written crop table that nobody could trace:
`crop_reference` was seeded directly into a Supabase project and the seed script
was never committed. This script replaces it with values derived from a public,
citable source, so anyone can regenerate the file and check it.

Source
------
ECOCROP: FAO Crop Ecological Requirements Database, archived on Zenodo.
    DOI  10.5281/zenodo.13319716
    https://zenodo.org/records/13319716
    Scraped from the original FAO ECOCROP data sheets by supersistence
    (github.com/supersistence/EcoCrop-ScrapeR).

The archive is "measurements or facts" format. For each taxon it carries optimal
growth temperature, optimal annual rainfall and optimal soil pH as a min/max
pair, distinguished by statisticalMethod:

    SIO_001113 -> minimum
    SIO_001114 -> maximum

Coverage
--------
Every taxon in the archive with a usable envelope is included — not a hand-picked
shortlist. Of the 2,567 taxa, 2,071 carry a complete temperature pair; two of
those are rejected as impossible (see PLAUSIBLE), and three pairs of synonyms
that share a common name are merged, leaving 2,066 rows. That set spans fruit,
vegetables, herbs, spices, nuts, grains, legumes, oilseeds, fodder, fibre, timber,
medicinal and ornamental plants.

The archive only carries scientific names, so common names are supplied for the
species a grower is likely to search for (see CURATED_NAMES) — 508 of the 2,066.
The other 1,558 keep their scientific name as the display name rather than being
dropped, because "I cannot name this in English" is not a reason to hide a plant
that has a real envelope. A row whose name is still Latin is visible as such, and
the catalogue can be searched by scientific name or family to reach it.

Two more columns make those unnamed rows usable. `family` is the botanical
family straight from the archive. `category` falls back to a genus or family
grouping (GENUS_CATEGORIES, FAMILY_CATEGORIES) where the plant's use is not in
doubt: 111 Eucalyptus species are timber, and every Leguminosae is a legume. That
still leaves 933 species under "Other" — mostly grasses, palms and 174 taxa the
archive carries no family for. They are browsable rather than hidden.

Source data is not trusted blindly. A handful of values in the archive are
transcription errors — a minimum temperature of 160 C, a 9000 mm rainfall
minimum against a 1300 mm maximum — and those are handled explicitly rather than
passed through or silently repaired.

What is derived vs. what is authored
------------------------------------
- Derived (from ECOCROP): min_temp, max_temp, min_rainfall_mm, max_rainfall_mm,
  min_ph, max_ph.
- Authored here (human judgement, not agronomic data): the species-to-common-name
  mapping and the category label. Common names and groupings are labels, not
  measurements, so they are not something a dataset can supply.

Rainfall and pH are written empty when the archive has no pair for them, rather
than defaulted to a plausible midpoint. The scorer renormalises its weights over
whatever is present and drops its confidence accordingly.

Usage
-----
    python backend/data/build_crop_data.py            # regenerate the CSV
    python backend/data/build_crop_data.py --check    # verify the CSV is current

The raw archive is downloaded into a gitignored scratch directory; only the
derived CSV is committed, because the archive is 10 MB and reproducible from
its DOI in one request.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ZENODO_ZIP = "https://zenodo.org/api/records/13319716/files/archive.zip/content"
SOURCE_NAME = "FAO ECOCROP via Zenodo 10.5281/zenodo.13319716"

HERE = Path(__file__).resolve().parent
OUT_CSV = HERE / "crop_reference.csv"
SCRATCH = HERE / ".ecocrop"
ARCHIVE = SCRATCH / "archive.zip"

# Common names and groupings for species a grower is likely to search for.
# This only overrides the label; it never decides whether a crop is included.
# Grouping is presentational.
CURATED_NAMES: dict[str, tuple[str, str]] = {
    # --- grains and staples ---
    "Zea mays": ("Maize", "Grain"),
    "Triticum aestivum": ("Wheat", "Grain"),
    "Hordeum vulgare": ("Barley", "Grain"),
    "Avena sativa": ("Oats", "Grain"),
    "Secale cereale": ("Rye", "Grain"),
    "Sorghum bicolor": ("Sorghum", "Grain"),
    "Pennisetum glaucum": ("Pearl millet", "Grain"),
    "Eleusine coracana ssp. coracana": ("Finger millet", "Grain"),
    "Eragrostis tef": ("Teff", "Grain"),
    "Oryza sativa": ("Rice", "Grain"),
    "Oryza glaberrima": ("African rice", "Grain"),
    "Panicum miliaceum": ("Proso millet", "Grain"),
    "Fagopyrum esculentum": ("Buckwheat", "Grain"),
    "Chenopodium quinoa": ("Quinoa", "Grain"),
    "Amaranthus caudatus": ("Amaranth", "Grain"),
    "Solanum tuberosum": ("Potato", "Staple"),
    "Ipomoea batatas": ("Sweet potato", "Staple"),
    "Manihot esculenta": ("Cassava", "Staple"),
    "Colocasia esculenta": ("Taro", "Staple"),
    "Dioscorea rotundata": ("Yam", "Staple"),
    "Dioscorea alata": ("Greater yam", "Staple"),
    "Xanthosoma sagittifolium": ("Tannia", "Staple"),
    "Canna indica": ("Canna", "Ornamental"),
    # --- legumes ---
    "Phaseolus vulgaris": ("Dry beans", "Legume"),
    "Phaseolus coccineus": ("Runner bean", "Legume"),
    "Phaseolus lunatus": ("Lima bean", "Legume"),
    "Pisum sativum": ("Peas", "Legume"),
    "Cicer arietinum": ("Chickpea", "Legume"),
    "Lens culinaris": ("Lentil", "Legume"),
    "Arachis hypogaea": ("Groundnut", "Legume"),
    "Glycine max": ("Soybean", "Legume"),
    "Vigna unguiculata": ("Cowpea", "Legume"),
    "Vigna radiata": ("Mung bean", "Legume"),
    "Vigna subterranea": ("Bambara groundnut", "Legume"),
    "Vicia faba": ("Faba bean", "Legume"),
    "Cajanus cajan": ("Pigeon pea", "Legume"),
    "Lablab purpureus": ("Lablab", "Legume"),
    "Macrotyloma uniflorum": ("Horse gram", "Legume"),
    "Mucuna pruriens": ("Velvet bean", "Fodder"),
    "Medicago sativa": ("Lucerne", "Fodder"),
    "Trifolium repens": ("White clover", "Fodder"),
    "Trifolium pratense": ("Red clover", "Fodder"),
    "Lupinus albus": ("White lupin", "Legume"),
    # --- oil and fibre ---
    "Helianthus annuus": ("Sunflower", "Oilseed"),
    "Brassica napus": ("Canola", "Oilseed"),
    "Brassica juncea": ("Brown mustard", "Oilseed"),
    "Sesamum indicum": ("Sesame", "Oilseed"),
    "Carthamus tinctorius": ("Safflower", "Oilseed"),
    "Ricinus communis": ("Castor bean", "Industrial"),
    "Olea europaea": ("Olive", "Fruit"),
    "Cocos nucifera": ("Coconut", "Fruit"),
    "Elaeis guineensis": ("Oil palm", "Industrial"),
    "Gossypium hirsutum": ("Cotton", "Fibre"),
    "Gossypium barbadense": ("Sea island cotton", "Fibre"),
    "Agave sisalana": ("Sisal", "Fibre"),
    "Linum usitatissimum": ("Flax", "Fibre"),
    "Boehmeria nivea": ("Ramie", "Fibre"),
    "Hibiscus cannabinus": ("Kenaf", "Fibre"),
    "Saccharum officinarum": ("Sugarcane", "Industrial"),
    "Beta vulgaris var. saccharifera": ("Sugar beet", "Industrial"),
    # --- leafy vegetables ---
    # ECOCROP indexes the cultivated form rather than the species for several
    # brassicas and for lettuce. These keys are the archive's own strings: a
    # curated entry only lands when it matches one, so "Brassica oleracea" on its
    # own named nothing and kale sat in the catalogue as Latin.
    "Spinacia oleracea": ("Spinach", "Vegetable"),
    "Beta vulgaris": ("Beetroot", "Vegetable"),
    "Beta vulgaris var. cicla": ("Swiss chard", "Vegetable"),
    "Beta vulgaris var. flavescens": ("Spinach beet", "Vegetable"),
    "Lactuca sativa var. capitata": ("Lettuce", "Vegetable"),
    "Brassica oleracea var. capitata": ("Cabbage", "Vegetable"),
    "Brassica oleracea var. botrytis": ("Cauliflower", "Vegetable"),
    "Brassica oleracea var. italica": ("Broccoli", "Vegetable"),
    "Brassica oleracea var. gemmifera": ("Brussels sprouts", "Vegetable"),
    "Brassica oleracea var. gongyloides": ("Kohlrabi", "Vegetable"),
    "Brassica oleracea var. acephala": ("Kale", "Vegetable"),
    "Brassica rapa Gaisin gr.": ("Chinese cabbage", "Vegetable"),
    "Brassica napus var. napobrassica": ("Swede", "Vegetable"),
    "Brassica campestris": ("Turnip rape", "Oilseed"),
    "Brassica carinata": ("Ethiopian mustard", "Oilseed"),
    "Brassica chinensis": ("Pak choi", "Vegetable"),
    "Brassica nigra": ("Black mustard", "Spice"),
    "Cichorium intybus": ("Chicory", "Vegetable"),
    "Cichorium endivia": ("Endive", "Vegetable"),
    "Apium graveolens": ("Celery", "Vegetable"),
    "Petroselinum crispum": ("Parsley", "Herb"),
    "Coriandrum sativum": ("Coriander", "Herb"),
    "Anethum graveolens": ("Dill", "Herb"),
    "Foeniculum vulgare": ("Fennel", "Herb"),
    "Ocimum basilicum": ("Basil", "Herb"),
    "Thymus vulgaris": ("Thyme", "Herb"),
    "Origanum vulgare": ("Oregano", "Herb"),
    "Rosmarinus officinalis": ("Rosemary", "Herb"),
    "Salvia officinalis": ("Sage", "Herb"),
    "Artemisia dracunculus": ("Tarragon", "Herb"),
    "Lavandula angustifolia": ("Lavender", "Herb"),
    "Amaranthus hybridus": ("Amaranth greens", "Vegetable"),
    "Amaranthus tricolor": ("Leaf amaranth", "Vegetable"),
    # Amaranth is what South African growers call morogo. Each species keeps its
    # own English name because a shared label would collapse four different
    # envelopes into one row; "morogo" is wired up as a search alias instead.
    "Amaranthus cruentus": ("Purple amaranth", "Vegetable"),
    "Amaranthus dubius": ("Slender amaranth", "Vegetable"),
    "Amaranthus hypochondriacus": ("Prince's feather", "Vegetable"),
    "Amaranthus lividus": ("Wild amaranth", "Vegetable"),
    "Chenopodium album": ("Fat hen", "Vegetable"),
    "Corchorus capsularis": ("Jute", "Fibre"),
    "Solanum nigrum": ("Black nightshade", "Vegetable"),
    "Portulaca oleracea": ("Purslane", "Vegetable"),
    "Urtica dioica": ("Stinging nettle", "Medicinal"),
    # --- root and bulb vegetables ---
    "Daucus carota": ("Carrot", "Vegetable"),
    "Pastinaca sativa": ("Parsnip", "Vegetable"),
    "Raphanus sativus": ("Radish", "Vegetable"),
    "Raphanus sativus var. radicula": ("Salad radish", "Vegetable"),
    "Allium cepa": ("Onion", "Vegetable"),
    "Allium fistulosum": ("Spring onion", "Vegetable"),
    "Allium sativum": ("Garlic", "Vegetable"),
    "Allium schoenoprasum": ("Chives", "Herb"),
    "Allium tuberosum": ("Garlic chives", "Herb"),
    "Allium chinense": ("Chinese scallion", "Vegetable"),
    "Apium graveolens var. rapaceum": ("Celeriac", "Vegetable"),
    "Arracacia xanthorrhiza": ("Arracacha", "Vegetable"),
    "Pachyrhizus erosus": ("Jicama", "Vegetable"),
    "Polymnia sonchifolia": ("Yacon", "Vegetable"),
    "Zingiber officinale": ("Ginger", "Spice"),
    "Curcuma longa": ("Turmeric", "Spice"),
    "Armoracia rusticana": ("Horseradish", "Spice"),
    # --- fruiting vegetables ---
    # Tomato is indexed under its older genus in ECOCROP; the Solanum name that
    # modern taxonomy uses is not in the archive at all.
    "Lycopersicon esculentum": ("Tomato", "Vegetable"),
    "Solanum melongena": ("Brinjal", "Vegetable"),
    "Capsicum annuum": ("Pepper", "Vegetable"),
    "Capsicum frutescens": ("Chilli", "Vegetable"),
    "Abelmoschus esculentus": ("Okra", "Vegetable"),
    "Abelmoschus manihot": ("Aibika", "Vegetable"),
    "Cucumis sativus": ("Cucumber", "Vegetable"),
    "Cucumis melo": ("Melon", "Vegetable"),
    "Citrullus lanatus": ("Watermelon", "Vegetable"),
    "Cucurbita maxima": ("Pumpkin", "Vegetable"),
    "Cucurbita pepo": ("Squash", "Vegetable"),
    "Cucurbita moschata": ("Butternut", "Vegetable"),
    "Cucurbita ficifolia": ("Fig-leaf gourd", "Vegetable"),
    "Lagenaria siceraria": ("Bottle gourd", "Vegetable"),
    "Luffa acutangula": ("Ridge gourd", "Vegetable"),
    "Momordica charantia": ("Bitter gourd", "Vegetable"),
    "Trichosanthes cucumerina": ("Snake gourd", "Vegetable"),
    "Sechium edule": ("Chayote", "Vegetable"),
    # Cape gooseberry is the South African name for this one; plain "gooseberry"
    # belongs to Ribes uva-crispa, which is a different plant.
    "Physalis peruviana": ("Cape gooseberry", "Fruit"),
    # Tamarillo. ECOCROP files it under its old genus; the Solanum betaceum name
    # is not in the archive, so a curated entry for that spelling lands nowhere.
    "Cyphomandra betacea": ("Tree tomato", "Fruit"),
    # --- deciduous and vine fruit ---
    "Vitis vinifera": ("Grape", "Fruit"),
    "Malus domestica": ("Apple", "Fruit"),
    "Pyrus communis": ("Pear", "Fruit"),
    "Prunus persica": ("Peach", "Fruit"),
    "Prunus armeniaca": ("Apricot", "Fruit"),
    "Prunus domestica": ("Plum", "Fruit"),
    "Prunus salicina": ("Japanese plum", "Fruit"),
    "Prunus avium": ("Cherry", "Fruit"),
    "Cydonia oblonga": ("Quince", "Fruit"),
    "Ficus carica": ("Fig", "Fruit"),
    "Fragaria x ananassa": ("Strawberry", "Fruit"),
    "Fragaria vesca": ("Alpine strawberry", "Fruit"),
    "Fragaria chiloensis": ("Chilean strawberry", "Fruit"),
    "Fragaria virginiana": ("Virginia strawberry", "Fruit"),
    "Rubus occidentalis x idaeus": ("Purple raspberry", "Fruit"),
    "Ribes rubrum": ("Red currant", "Fruit"),
    "Ribes nigrum": ("Black currant", "Fruit"),
    "Ribes sativum": ("White currant", "Fruit"),
    "Ribes uva-crispa": ("Gooseberry", "Fruit"),
    "Ribes hirtellum": ("American gooseberry", "Fruit"),
    "Vaccinium corymbosum": ("Blueberry", "Fruit"),
    "Vaccinium angustifolium": ("Lowbush blueberry", "Fruit"),
    "Vaccinium macrocarpon": ("Cranberry", "Fruit"),
    "Vaccinium myrtillus": ("Bilberry", "Fruit"),
    "Malus sylvestris": ("Crab apple", "Fruit"),
    "Punica granatum": ("Pomegranate", "Fruit"),
    "Diospyros kaki": ("Persimmon", "Fruit"),
    "Morus alba": ("Mulberry", "Fruit"),
    "Morus nigra": ("Black mulberry", "Fruit"),
    # --- citrus ---
    "Citrus limon": ("Lemon", "Fruit"),
    "Citrus sinensis": ("Orange", "Fruit"),
    "Citrus reticulata": ("Mandarin", "Fruit"),
    "Citrus paradisi": ("Grapefruit", "Fruit"),
    "Citrus aurantium": ("Seville orange", "Fruit"),
    "Citrus aurantifolia": ("Lime", "Fruit"),
    "Citrus latifolia": ("Tahiti lime", "Fruit"),
    # --- subtropical and tropical fruit ---
    "Persea americana": ("Avocado", "Fruit"),
    "Mangifera indica": ("Mango", "Fruit"),
    "Musa acuminata": ("Banana", "Fruit"),
    "Musa acuminata x balbisiana": ("Banana (hybrid)", "Fruit"),
    "Psidium guajava": ("Guava", "Fruit"),
    "Ananas comosus": ("Pineapple", "Fruit"),
    "Passiflora edulis": ("Granadilla", "Fruit"),
    "Passiflora ligularis": ("Sweet granadilla", "Fruit"),
    "Carica papaya": ("Papaya", "Fruit"),
    "Litchi chinensis": ("Litchi", "Fruit"),
    "Dimocarpus longan var. longan": ("Longan", "Fruit"),
    "Dimocarpus longan var. malesianus": ("Longan (maleisan)", "Fruit"),
    "Nephelium lappaceum": ("Rambutan", "Fruit"),
    "Annona cherimola": ("Cherimoya", "Fruit"),
    "Annona squamosa": ("Sugar apple", "Fruit"),
    "Annona muricata": ("Soursop", "Fruit"),
    "Artocarpus heterophyllus": ("Jackfruit", "Fruit"),
    "Artocarpus altilis": ("Breadfruit", "Fruit"),
    "Averrhoa carambola": ("Star fruit", "Fruit"),
    "Eugenia jambos": ("Rose apple", "Fruit"),
    "Tamarindus indica": ("Tamarind", "Fruit"),
    "Phoenix dactylifera": ("Date palm", "Fruit"),
    "Hylocereus undatus": ("Dragon fruit", "Fruit"),
    "Actinidia chinensis": ("Kiwifruit", "Fruit"),
    "Actinidia arguta": ("Kiwiberry", "Fruit"),
    "Opuntia ficus-indica": ("Prickly pear", "Fruit"),
    "Dovyalis caffra": ("Kei apple", "Fruit"),
    "Vangueria infausta": ("Wild medlar", "Fruit"),
    "Vangueria madagascariensis": ("Spanish tamarind", "Fruit"),
    "Ximenia americana": ("Sour plum", "Fruit"),
    "Adansonia digitata": ("Baobab", "Fruit"),
    "Ziziphus mauritiana": ("Jujube", "Fruit"),
    # --- nuts ---
    "Juglans regia": ("Walnut", "Nut"),
    "Corylus avellana": ("Hazelnut", "Nut"),
    "Castanea sativa": ("Chestnut", "Nut"),
    "Pistacia vera": ("Pistachio", "Nut"),
    "Anacardium occidentale": ("Cashew", "Nut"),
    "Macadamia integrifolia": ("Macadamia", "Nut"),
    "Carya illinoensis": ("Pecan", "Nut"),
    "Bertholletia excelsa": ("Brazil nut", "Nut"),
    # --- beverage and spice ---
    "Coffea arabica": ("Coffee", "Beverage"),
    "Coffea canephora": ("Robusta coffee", "Beverage"),
    "Camellia sinensis": ("Tea", "Beverage"),
    "Theobroma cacao": ("Cocoa", "Beverage"),
    "Humulus lupulus": ("Hops", "Beverage"),
    "Piper nigrum": ("Black pepper", "Spice"),
    "Eugenia aromatica": ("Clove", "Spice"),
    "Myristica fragrans": ("Nutmeg", "Spice"),
    "Cinnamomum verum": ("Cinnamon", "Spice"),
    "Cinnamomum cassia": ("Cassia", "Spice"),
    "Elettaria cardamomum": ("Cardamom", "Spice"),
    "Vanilla planifolia": ("Vanilla", "Spice"),
    "Crocus sativus": ("Saffron", "Spice"),
    "Pimpinella anisum": ("Anise", "Spice"),
    "Carum carvi": ("Caraway", "Spice"),
    "Nigella sativa": ("Black cumin", "Spice"),
    "Cuminum cyminum": ("Cumin", "Spice"),
    "Trachyspermum ammi": ("Ajwain", "Spice"),
    "Anthriscus cerefolium": ("Chervil", "Herb"),
    "Levisticum officinale": ("Lovage", "Herb"),
    "Melissa officinalis": ("Lemon balm", "Herb"),
    "Origanum majorana": ("Marjoram", "Herb"),
    "Satureja hortensis": ("Summer savory", "Herb"),
    "Thymus serpyllum": ("Wild thyme", "Herb"),
    "Ocimum tenuiflorum": ("Holy basil", "Herb"),
    "Perilla frutescens": ("Perilla", "Herb"),
    "Hyssopus officinalis": ("Hyssop", "Herb"),
    "Aloysia triphylla": ("Lemon verbena", "Herb"),
    "Aframomum melegueta": ("Grains of paradise", "Spice"),
    "Alpinia galanga": ("Greater galangal", "Spice"),
    "Alpinia officinarum": ("Lesser galangal", "Spice"),
    "Curcuma zedoaria": ("Zedoary", "Spice"),
    "Artemisia afra": ("African wormwood", "Medicinal"),
    "Moringa oleifera": ("Moringa", "Vegetable"),
    "Aloe ferox": ("Bitter aloe", "Medicinal"),
    "Aloe barbadensis": ("Aloe vera", "Medicinal"),
    "Stevia rebaudiana": ("Stevia", "Herb"),
    "Matricaria recutita": ("Chamomile", "Herb"),
    "Echinacea purpurea": ("Coneflower", "Medicinal"),
    "Taraxacum officinale": ("Dandelion", "Medicinal"),
    "Silybum marianum": ("Milk thistle", "Medicinal"),
    "Vernonia amygdalina": ("Bitter leaf", "Vegetable"),
    "Cynara scolymus": ("Globe artichoke", "Vegetable"),
    "Cynara cardunculus": ("Cardoon", "Vegetable"),
    # --- fodder and pasture ---
    "Zea mays ssp. saccharata": ("Sweet corn", "Vegetable"),
    "Sorghum x drummondii": ("Sudan grass", "Fodder"),
    "Pennisetum purpureum": ("Elephant grass", "Fodder"),
    "Pennisetum clandestinum": ("Kikuyu grass", "Fodder"),
    "Panicum maximum": ("Guinea grass", "Fodder"),
    "Chloris gayana": ("Rhodes grass", "Fodder"),
    "Digitaria eriantha ssp. eriantha": ("Smuts finger grass", "Fodder"),
    "Eragrostis curvula": ("Weeping lovegrass", "Fodder"),
    "Cenchrus ciliaris": ("Buffel grass", "Fodder"),
    "Lolium perenne": ("Perennial ryegrass", "Fodder"),
    "Dactylis glomerata": ("Cocksfoot", "Fodder"),
    "Festuca arundinacea": ("Tall fescue", "Fodder"),
    "Vicia villosa ssp. villosa": ("Hairy vetch", "Fodder"),
    "Atriplex nummularia": ("Old man saltbush", "Fodder"),
    "Leucaena leucocephala": ("Leucaena", "Fodder"),
    "Gliricidia sepium": ("Gliricidia", "Fodder"),
    "Sesbania sesban": ("Sesbania", "Fodder"),
    "Desmodium intortum": ("Greenleaf desmodium", "Fodder"),
    # --- timber and agroforestry ---
    "Eucalyptus grandis": ("Flooded gum", "Timber"),
    "Eucalyptus camaldulensis": ("River red gum", "Timber"),
    "Pinus radiata": ("Radiata pine", "Timber"),
    "Pinus patula": ("Patula pine", "Timber"),
    "Acacia mearnsii": ("Black wattle", "Timber"),
    "Acacia mangium": ("Mangium", "Timber"),
    "Grevillea robusta": ("Grevillea", "Timber"),
    "Casuarina equisetifolia": ("Beefwood", "Timber"),
    "Tectona grandis": ("Teak", "Timber"),
    "Swietenia macrophylla": ("Mahogany", "Timber"),
    "Populus deltoides": ("Eastern cottonwood", "Timber"),
    "Azadirachta indica": ("Neem", "Medicinal"),
    "Faidherbia albida": ("Ana tree", "Timber"),
    # --- ornamental, cut flower and nursery ---
    # ECOCROP is a crop database, not a nursery catalogue: most cut flowers (roses,
    # tulips, chrysanthemums, Strelitzia, agapanthus) are simply not in it. Only
    # the ornamentals the archive actually covers are named here.
    "Calendula officinalis": ("Calendula", "Ornamental"),
    "Myrtus communis": ("Myrtle", "Ornamental"),
    "Melaleuca quinquenervia": ("Paperbark", "Ornamental"),
    "Acmena smithii": ("Lilly pilly", "Ornamental"),
    "Sansevieria guineensis": ("Snake plant", "Ornamental"),
    "Yucca elephantipes": ("Spineless yucca", "Ornamental"),
    "Bougainvillea glabra": ("Bougainvillea", "Ornamental"),
    "Delonix regia": ("Flamboyant tree", "Ornamental"),
    "Jacaranda mimosifolia": ("Jacaranda", "Ornamental"),
    "Schinus molle": ("Pepper tree", "Ornamental"),
    "Helianthus tuberosus": ("Jerusalem artichoke", "Vegetable"),
    # --- industrial and multipurpose ---
    "Jatropha curcas": ("Physic nut", "Industrial"),
    "Parthenium argentatum": ("Guayule", "Industrial"),
    "Simmondsia chinensis": ("Jojoba", "Industrial"),
    "Cymbopogon citratus": ("Lemongrass", "Herb"),
    "Vetiveria zizanioides": ("Vetiver", "Industrial"),
    "Bambusa vulgaris": ("Bamboo", "Timber"),
    "Nicotiana tabacum": ("Tobacco", "Industrial"),
    "Hevea brasiliensis": ("Rubber tree", "Industrial"),
    "Agave fourcroydes": ("Henequen", "Fibre"),
    "Agave cantala": ("Cantala", "Fibre"),
    "Musa textilis": ("Abaca", "Fibre"),
    "Ceiba pentandra": ("Kapok", "Fibre"),
    "Ochroma pyramidale": ("Balsa", "Timber"),
    "Tilia cordata": ("Small-leaved lime", "Timber"),

    # --- archive-name aliases ---
    # ECOCROP indexes several species under an older synonym. These entries exist
    # so the labels still land on the row the archive actually carries; without
    # them the crop is included but shows up under its Latin name.
    "Sclerocarya birrea ssp. caffra": ("Marula", "Fruit"),
    "Sclerocarya caffra": ("Marula", "Fruit"),
    "Protea caffra ssp. caffra": ("Protea", "Ornamental"),
    "Syzygium cordatum": ("Waterberry", "Fruit"),
    "Syzygium guineense": ("Water pear", "Fruit"),
    "Syzygium cumini": ("Java plum", "Fruit"),
    "Rubus idaeus ssp. idaeus": ("Raspberry", "Fruit"),
    "Mentha piperita": ("Peppermint", "Herb"),
    "Mentha spicata var. crispa": ("Spearmint", "Herb"),
    "Allium ampeloprasum": ("Leek", "Vegetable"),
    "Allium cepa var. aggregatum": ("Shallot", "Vegetable"),
    "Eruca sativa": ("Rocket", "Vegetable"),
    "Brassica rapa var. rapifera": ("Turnip", "Vegetable"),
    "Brassica rapa Pak Choi": ("Pak choi", "Vegetable"),
    "Musa balbisiana": ("Plantain", "Fruit"),
    "Citrus medica": ("Citron", "Fruit"),
    "Citrus grandis": ("Pomelo", "Fruit"),
    "Hibiscus sabdariffa": ("Roselle", "Beverage"),
    "Hibiscus sabdariffa var. sabdariffa": ("Roselle (cultivated)", "Beverage"),
    "Sorghum bicolor var. sweet": ("Sweet sorghum", "Fodder"),

    # --- second pass: edibles the first shortlist missed --------------------
    # The first pass covered what a South African field officer would name off
    # the top of their head. These are the species that were in the catalogue
    # but hidden behind a Latin name, which made the whole set look far smaller
    # than it is. The build reports any curated name that does not land on a row,
    # which is how the wrong-spelling entries here were found and fixed.
    "Annona reticulata": ("Custard apple", "Fruit"),
    "Annona atemoya": ("Atemoya", "Fruit"),
    "Annona senegalensis": ("Wild custard apple", "Fruit"),
    "Annona montana": ("Mountain soursop", "Fruit"),
    "Annona diversifolia": ("Ilama", "Fruit"),
    "Annona purpurea": ("Soncoya", "Fruit"),
    "Asimina triloba": ("American pawpaw", "Fruit"),
    "Cananga odorata": ("Ylang-ylang", "Industrial"),
    "Spondias cytherea": ("Ambarella", "Fruit"),
    "Spondias mombin": ("Hog plum", "Fruit"),
    "Spondias purpurea": ("Red mombin", "Fruit"),
    "Pistacia lentiscus": ("Mastic tree", "Industrial"),
    "Diospyros mespiliformis": ("Jackalberry", "Fruit"),
    "Diospyros virginiana": ("American persimmon", "Fruit"),
    "Diospyros digyna": ("Black sapote", "Fruit"),
    "Diospyros malabarica": ("Gaub", "Fruit"),
    "Dovyalis hebecarpa": ("Ceylon gooseberry", "Fruit"),
    "Flacourtia indica": ("Governor's plum", "Fruit"),
    "Pangium edule": ("Keluak", "Spice"),
    "Garcinia mangostana": ("Mangosteen", "Fruit"),
    "Garcinia dulcis": ("Mundu", "Fruit"),
    "Garcinia xanthochymus": ("Yellow mangosteen", "Fruit"),
    "Mammea americana": ("Mammee apple", "Fruit"),
    "Laurus nobilis": ("Bay laurel", "Spice"),
    "Cinnamomum burmannii": ("Indonesian cinnamon", "Spice"),
    "Cinnamomum loureirii": ("Saigon cinnamon", "Spice"),
    "Cinnamomum camphora": ("Camphor tree", "Industrial"),
    "Persea americana ssp. guatemalan": ("Avocado (Guatemalan race)", "Fruit"),
    "Persea americana ssp. mexican": ("Avocado (Mexican race)", "Fruit"),
    "Persea americana ssp. west indian": ("Avocado (West Indian race)", "Fruit"),
    "Artocarpus integer": ("Chempedak", "Fruit"),
    "Artocarpus lakoocha": ("Monkey jack", "Fruit"),
    "Morus rubra": ("Red mulberry", "Fruit"),
    "Ficus sycomorus": ("Sycamore fig", "Fruit"),
    "Acca sellowiana": ("Feijoa", "Fruit"),
    "Pimenta dioica": ("Allspice", "Spice"),
    "Pimenta racemosa": ("Bay rum tree", "Industrial"),
    "Psidium cattleianum": ("Strawberry guava", "Fruit"),
    "Eugenia uniflora": ("Surinam cherry", "Fruit"),
    "Eugenia dombeyi": ("Grumichama", "Fruit"),
    "Syzygium malaccense": ("Malay apple", "Fruit"),
    "Syzygium javanicum": ("Java apple", "Fruit"),
    "Myrciaria cauliflora": ("Jaboticaba", "Fruit"),
    "Eriobotrya japonica": ("Loquat", "Fruit"),
    "Prunus amygdalus": ("Almond", "Nut"),
    "Prunus cerasus": ("Sour cherry", "Fruit"),
    "Prunus mume": ("Japanese apricot", "Fruit"),
    "Prunus capuli": ("Capulin cherry", "Fruit"),
    "Prunus africana": ("African cherry", "Medicinal"),
    "Pyrus pyrifolia": ("Nashi pear", "Fruit"),
    "Sorbus domestica": ("Service tree", "Fruit"),
    "Rubus occidentalis": ("Black raspberry", "Fruit"),
    "Hagenia abyssinica": ("African redwood", "Medicinal"),
    "Aegle marmelos": ("Bael", "Fruit"),
    "Calodendrum capense": ("Cape chestnut", "Ornamental"),
    "Casimiroa edulis": ("White sapote", "Fruit"),
    "Citrus aurantium ssp. bergamia": ("Bergamot", "Fruit"),
    "Citrus deliciosa": ("Mediterranean mandarin", "Fruit"),
    "Citrus madurensis": ("Calamondin", "Fruit"),
    "Citrus unshiu": ("Satsuma mandarin", "Fruit"),
    "Fortunella margarita": ("Kumquat", "Fruit"),
    "Fortunella japonica": ("Round kumquat", "Fruit"),
    "Fortunella hindsii": ("Hong Kong kumquat", "Ornamental"),
    "Clausena lansium": ("Wampee", "Fruit"),
    "Murraya koenigii": ("Curry leaf", "Herb"),
    "Ruta graveolens": ("Rue", "Herb"),
    "Zanthoxylum chalybeum": ("Knobwood", "Spice"),
    "Blighia sapida": ("Ackee", "Fruit"),
    "Melicoccus bijugatus": ("Spanish lime", "Fruit"),
    "Nephelium mutabile": ("Pulasan", "Fruit"),
    "Paullinia cupana": ("Guarana", "Beverage"),
    "Capsicum chinense": ("Habanero chilli", "Vegetable"),
    "Capsicum baccatum var. pendulum": ("Aji amarillo", "Vegetable"),
    "Capsicum pubescens": ("Rocoto", "Vegetable"),
    "Physalis philadelphica": ("Tomatillo", "Vegetable"),
    "Solanum aethiopicum": ("African eggplant", "Vegetable"),
    "Solanum macrocarpon": ("Gboma eggplant", "Vegetable"),
    "Solanum muricatum": ("Pepino", "Fruit"),
    "Solanum quitoense": ("Naranjilla", "Fruit"),
    "Solanum torvum": ("Turkey berry", "Vegetable"),
    "Solanum americanum": ("Black nightshade", "Vegetable"),
    "Solanum incanum": ("Bitter apple", "Medicinal"),
    "Withania somnifera": ("Ashwagandha", "Medicinal"),
    "Lycium chinense": ("Goji", "Medicinal"),
    "Cola acuminata": ("Kola nut", "Beverage"),
    "Cola nitida": ("Bitter kola", "Beverage"),
    "Theobroma grandiflorum": ("Cupuacu", "Fruit"),
    "Theobroma bicolor": ("Mocambo", "Fruit"),
    "Brachychiton acerifolius": ("Illawarra flame tree", "Ornamental"),
    "Vitis labrusca": ("Concord grape", "Fruit"),
    "Vitis rotundifolia": ("Muscadine grape", "Fruit"),
    "Passiflora edulis var. edulis": ("Purple passion fruit", "Fruit"),
    "Passiflora edulis var. flavicarpa": ("Yellow passion fruit", "Fruit"),
    "Passiflora mollissima": ("Banana passion fruit", "Fruit"),
    "Passiflora quadrangularis": ("Giant granadilla", "Fruit"),
    "Passiflora laurifolia": ("Water lemon", "Fruit"),
    "Averrhoa bilimbi": ("Bilimbi", "Fruit"),
    "Oxalis tuberosa": ("Oca", "Staple"),
    "Carica pubescens": ("Mountain papaya", "Fruit"),
    "Benincasa hispida": ("Wax gourd", "Vegetable"),
    "Citrullus colocynthis": ("Colocynth", "Medicinal"),
    "Cucumis anguria": ("West Indian gherkin", "Vegetable"),
    "Cucurbita mixta": ("Green-striped cushaw", "Vegetable"),
    "Luffa cylindrica": ("Luffa", "Industrial"),
    "Momordica cochinchinensis": ("Gac", "Fruit"),
    "Telfairia occidentalis": ("Fluted pumpkin", "Vegetable"),
    "Telfairia pedata": ("Oyster nut", "Nut"),
    "Asparagus officinalis": ("Asparagus", "Vegetable"),
    "Strychnos spinosa": ("Spiny monkey orange", "Fruit"),
    "Ensete ventricosum": ("Ethiopian banana", "Staple"),
    "Tylosema esculentum": ("Marama bean", "Legume"),
    "Abelmoschus moschatus": ("Musk mallow", "Industrial"),
    "Gossypium arboreum": ("Tree cotton", "Fibre"),
    "Gossypium herbaceum": ("Levant cotton", "Fibre"),
    "Hibiscus sabdariffa var. altissima": ("Roselle (fibre type)", "Fibre"),
    "Urena lobata": ("Caesarweed", "Fibre"),

    # --- third pass: staples, palms and tropical fruit still under Latin -------
    # Same rule as above: a name is only added when the plant is something a
    # grower buys, plants or sells. Both Manilkara species are sapodilla, so only
    # one is named rather than merging two envelopes into a single row.
    # yams and aroids
    "Dioscorea bulbifera": ("Air potato", "Staple"),
    "Dioscorea cayenensis": ("Yellow guinea yam", "Staple"),
    "Dioscorea dumetorum": ("Bitter yam", "Staple"),
    "Dioscorea esculenta": ("Lesser yam", "Staple"),
    "Dioscorea opposita": ("Chinese yam", "Staple"),
    "Dioscorea trifida": ("Cush-cush yam", "Staple"),
    "Alocasia macrorrhizos": ("Giant taro", "Staple"),
    "Xanthosoma brasiliense": ("Tahitian spinach", "Staple"),
    # palms
    "Phoenix reclinata": ("Wild date palm", "Fruit"),
    "Borassus aethiopum": ("African fan palm", "Fruit"),
    "Borassus flabellifer": ("Palmyra palm", "Fruit"),
    "Hyphaene thebaica": ("Doum palm", "Fruit"),
    "Euterpe oleracea": ("Acai", "Fruit"),
    "Bactris gasipaes": ("Peach palm", "Fruit"),
    "Salacca zalacca": ("Salak", "Fruit"),
    "Mauritia flexuosa": ("Buriti palm", "Fruit"),
    "Areca catechu": ("Betel nut", "Industrial"),
    "Metroxylon sagu": ("Sago palm", "Staple"),
    "Nypa fruticans": ("Nipa palm", "Industrial"),
    "Raphia hookeri": ("Raphia palm", "Fibre"),
    "Caryota urens": ("Fish-tail palm", "Timber"),
    "Acrocomia aculeata": ("Macaw palm", "Industrial"),
    "Attalea funifera": ("Piassava", "Fibre"),
    "Calamus caesius": ("Rattan", "Timber"),
    "Elaeis oleifera": ("American oil palm", "Industrial"),
    "Serenoa repens": ("Saw palmetto", "Medicinal"),
    "Chamaerops humilis": ("Dwarf fan palm", "Ornamental"),
    "Livistona australis": ("Australian fan palm", "Ornamental"),
    # sapotaceae and other tropical fruit
    "Manilkara zapota": ("Sapodilla", "Fruit"),
    "Chrysophyllum cainito": ("Star apple", "Fruit"),
    "Chrysophyllum albidum": ("African star apple", "Fruit"),
    "Vitellaria paradoxa": ("Shea tree", "Industrial"),
    "Argania sideroxylon": ("Argan", "Industrial"),
    "Uapaca kirkiana": ("Wild loquat", "Fruit"),
    "Antidesma bunius": ("Bignay", "Fruit"),
    "Baccaurea ramiflora": ("Burmese grape", "Fruit"),
    "Dacryodes edulis": ("African plum", "Fruit"),
    "Canarium ovatum": ("Pili nut", "Nut"),
    "Canarium indicum": ("Ngali nut", "Nut"),
    "Durio zibethinus": ("Durian", "Fruit"),
    "Brosimum alicastrum": ("Breadnut", "Nut"),
    "Muntingia calabura": ("Jamaican cherry", "Fruit"),
    "Grewia asiatica": ("Phalsa", "Fruit"),
    "Eugenia uvalha": ("Uvaia", "Fruit"),
    "Psidium friedrichsthalianum": ("Costa Rican guava", "Fruit"),
    # leafy greens, coffee and industrial
    "Cnidoscolus chayamansa": ("Chaya", "Vegetable"),
    "Sauropus androgynus": ("Katuk", "Vegetable"),
    "Solanum oleraceum": ("African garden egg", "Vegetable"),
    "Solanum ferox": ("Hairy eggplant", "Vegetable"),
    "Boesenbergia rotunda": ("Fingerroot", "Spice"),
    "Aframomum corrorima": ("Ethiopian cardamom", "Spice"),
    "Coffea liberica": ("Liberica coffee", "Beverage"),
    "Coffea excelsa": ("Excelsa coffee", "Beverage"),
    "Morinda citrifolia": ("Noni", "Medicinal"),
    "Aleurites moluccana": ("Candlenut", "Industrial"),
    "Euphorbia tirucalli": ("Rubber hedge", "Industrial"),
    "Ficus thonningii": ("Common wild fig", "Timber"),
    "Bridelia micrantha": ("Coast goldleaf", "Timber"),
    "Carissa macrocarpa": ("Big num-num", "Fruit"),
    "Carissa edulis": ("Num-num", "Fruit"),
}

# Category from the genus alone, for species the curated list does not name.
#
# This is grouping, not labelling: it never invents a common name, and it only
# covers genera whose use is unambiguous. 111 Eucalyptus species are not 111
# errors in the catalogue - they are a forestry genus - and saying so is more
# honest than filing them all under "Other".
GENUS_CATEGORIES: dict[str, str] = {
    **{genus: "Timber" for genus in (
        "Eucalyptus", "Corymbia", "Angophora", "Melaleuca", "Syncarpia",
        "Lophostemon", "Tristania", "Pinus", "Araucaria", "Agathis",
        "Cupressus", "Thuja", "Cedrus", "Picea", "Abies", "Larix",
        "Pseudotsuga", "Tectona", "Dalbergia", "Shorea", "Dipterocarpus",
        "Hopea", "Vatica", "Parashorea", "Dryobalanops", "Quercus", "Fagus",
        "Fraxinus", "Betula", "Alnus", "Populus", "Salix", "Ulmus",
        "Tilia", "Juglans", "Casuarina",
    )},
    # South African fynbos and garden genera. Ornamental is what they are sold
    # for, which is the question this category answers.
    **{genus: "Ornamental" for genus in (
        "Protea", "Leucospermum", "Leucadendron", "Mimetes", "Erica",
        "Agapanthus", "Kniphofia", "Watsonia", "Crocosmia", "Gladiolus",
        "Clivia", "Dietes", "Strelitzia", "Zantedeschia", "Tulbaghia",
        "Agave", "Yucca", "Rosa", "Chrysanthemum", "Dahlia", "Tagetes",
        "Narcissus", "Tulipa", "Lilium", "Iris", "Anthurium", "Heliconia",
        "Canna", "Bougainvillea", "Hibiscus", "Impatiens", "Begonia",
    )},
    "Aloe": "Medicinal",
}

# Family-level grouping, used only where the family *is* the answer. Every
# Leguminosae is a legume; that is a fact about the plant, not a guess about its
# use. Grasses and palms are left unclassified because "cereal", "forage" and
# "thatch" are all Gramineae, so the family does not settle the category.
FAMILY_CATEGORIES: dict[str, str] = {
    "Leguminosae": "Legume",
}

DERIVED_PROPERTIES = {
    "OptimalGrowthTemperature": ("min_temp", "max_temp"),
    "optimal_rainfall": ("min_rainfall_mm", "max_rainfall_mm"),
    "OptimalGrowthpH": ("min_ph", "max_ph"),
}

# Temperature is the signal the scorer always uses, so a taxon without it cannot
# be scored at all. Rainfall and pH are optional: the archive simply lacks them
# for some species, and inventing a midpoint would be fabrication.
REQUIRED_PROPERTY = "OptimalGrowthTemperature"

FIELDS = [
    "name", "scientific_name", "family", "category",
    "min_temp", "max_temp",
    "min_rainfall_mm", "max_rainfall_mm",
    "min_ph", "max_ph",
    "source",
]

UNCATEGORISED = "Other"


def fetch_archive() -> Path:
    """Download the ECOCROP archive once into a gitignored scratch dir."""
    if ARCHIVE.exists() and ARCHIVE.stat().st_size > 100_000:
        return ARCHIVE
    SCRATCH.mkdir(parents=True, exist_ok=True)
    print(f"downloading {ZENODO_ZIP}", file=sys.stderr)
    with urllib.request.urlopen(ZENODO_ZIP, timeout=120) as response:
        ARCHIVE.write_bytes(response.read())
    return ARCHIVE


def read_archive(path: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    """Return (taxonID -> {scientific, family}, measurement rows)."""
    with zipfile.ZipFile(path) as archive:
        taxa_rows = list(csv.DictReader(
            io.TextIOWrapper(archive.open("taxa.txt"), encoding="utf-8", errors="ignore"),
            delimiter="\t",
        ))
        measurements = list(csv.DictReader(
            io.TextIOWrapper(archive.open("measurementsorfacts.txt"), encoding="utf-8", errors="ignore"),
            delimiter="\t",
        ))
    taxa = {
        row["taxonID"]: {
            "scientific": (row.get("scientificName") or "").strip(),
            # Botanical family, straight from the archive. It is the one piece of
            # identity available for the ~1,800 species with no common name, so a
            # grower browsing the catalogue still sees what kind of plant it is.
            "family": (row.get("family") or "").strip(),
        }
        for row in taxa_rows
    }
    return taxa, measurements


def _fallback_category(scientific: str, family: str) -> str:
    """Category for a species the curated list does not name.

    Genus first, then family, then Other. Neither step invents a name: they only
    say what kind of plant it is, which is the question a grower browsing 2,000
    species is actually asking.
    """
    genus = scientific.split()[0] if scientific else ""
    return (
        GENUS_CATEGORIES.get(genus)
        or FAMILY_CATEGORIES.get(family)
        or UNCATEGORISED
    )


def _clean_number(value: str) -> str:
    """Normalise an archive number to a plain decimal string, or '' if unusable."""
    text = (value or "").strip().replace(",", ".")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return ""
    if number != number:  # NaN
        return ""
    return f"{number:g}"


# The archive is a scrape of FAO's published sheets and carries a few
# transcription errors. Barringtonia racemosa is recorded with a minimum growth
# temperature of 160 and Eugenia stipitata with 2000-3500, both against a unit of
# degrees Celsius; Carissa edulis carries a 9000 mm rainfall minimum.
#
# These are rejected rather than repaired. Guessing that 160 means 16, or that a
# 9000 came from a stray zero, would be inventing agronomic data in a project
# whose whole point is that every number is traceable.
#
# The windows are deliberately very wide: they exist to catch impossible values,
# not to second-guess unusual but real ones.
PLAUSIBLE = {
    "OptimalGrowthTemperature": (-15.0, 60.0),   # degrees C
    "optimal_rainfall": (0.0, 20000.0),          # mm per year
    "OptimalGrowthpH": (2.0, 11.0),
}


def _is_plausible(prop: str, bounds: dict[str, str]) -> bool:
    """True if the envelope is complete, correctly ordered and physically possible."""
    low_text = bounds.get("min") or ""
    high_text = bounds.get("max") or ""
    if not low_text or not high_text:
        return False
    low, high = float(low_text), float(high_text)
    if low > high:
        return False
    floor, ceiling = PLAUSIBLE[prop]
    return floor <= low and high <= ceiling


def build_rows(
    taxa: dict[str, dict[str, str]],
    measurements: list[dict[str, str]],
    *,
    verbose: bool = False,
) -> list[dict[str, str]]:
    # (taxonID, property) -> {"min": value, "max": value}
    envelopes: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for row in measurements:
        tid = (row.get("occurrenceID") or "").strip()
        if tid not in taxa:
            continue
        prop = (row.get("measurementType") or "").rsplit("/", 1)[-1]
        if prop not in DERIVED_PROPERTIES:
            continue
        method = row.get("statisticalMethod") or ""
        if "SIO_001113" in method:
            bound = "min"
        elif "SIO_001114" in method:
            bound = "max"
        else:
            continue
        number = _clean_number(row.get("measurementValue") or "")
        if number:
            envelopes[(tid, prop)][bound] = number

    rejected: list[str] = []
    dropped: list[str] = []

    candidates: list[dict[str, str]] = []
    for tid, taxon in taxa.items():
        scientific = taxon["scientific"]
        required = envelopes.get((tid, REQUIRED_PROPERTY), {})
        if "min" not in required or "max" not in required:
            continue
        if not _is_plausible(REQUIRED_PROPERTY, required):
            # Without a usable temperature window the species cannot be scored at
            # all, so the row is dropped and the reason is reported.
            rejected.append(f"{scientific} ({required.get('min')}-{required.get('max')} C)")
            continue

        curated = CURATED_NAMES.get(scientific)
        record = {
            "name": curated[0] if curated else scientific,
            "scientific_name": scientific,
            "family": taxon["family"],
            "category": curated[1] if curated else _fallback_category(scientific, taxon["family"]),
            "source": SOURCE_NAME,
        }

        usable = 0
        for prop, (min_field, max_field) in DERIVED_PROPERTIES.items():
            bounds = envelopes.get((tid, prop), {})
            if _is_plausible(prop, bounds):
                usable += 1
                record[min_field] = bounds["min"]
                record[max_field] = bounds["max"]
            else:
                # A broken optional envelope loses the envelope, not the species:
                # the crop can still be scored on its temperature window, and the
                # scorer renormalises over what is present.
                record[min_field] = ""
                record[max_field] = ""
                if bounds:
                    dropped.append(
                        f"{scientific} {prop.replace('OptimalGrowth', '').lower()} "
                        f"{bounds.get('min', '?')}-{bounds.get('max', '?')}"
                    )

        # Completeness is only used to choose between two taxa sharing a common
        # name; it never excludes a crop.
        record["_completeness"] = str(usable)
        candidates.append(record)

    # Lycopersicon esculentum and Solanum lycopersicum are both "Tomato", and two
    # Macadamia species share a name too. Scientific names are unique per taxon,
    # so the only possible collisions are curated common names: keep whichever
    # carries more complete envelope data. Uncurated taxa keep their Latin name
    # and are never dropped.
    by_name: dict[str, dict[str, str]] = {}
    merged: list[tuple[str, str]] = []
    for record in sorted(candidates, key=lambda r: (-int(r["_completeness"]), r["scientific_name"])):
        if record["name"] in by_name:
            merged.append((record["scientific_name"], record["name"]))
            continue
        by_name[record["name"]] = record

    rows = []
    for record in sorted(by_name.values(), key=lambda r: (r["category"], r["name"])):
        record.pop("_completeness", None)
        rows.append(record)

    # A row dropped for impossible data is a defect in the source, not something
    # routine, so it is always named. These are the species a reader should know
    # are missing rather than wonder about.
    for line in rejected:
        print(f"warning: dropped {line} - value is not physically possible", file=sys.stderr)

    # A dropped optional envelope is minor: the crop is still listed and scored on
    # temperature. Listed only under --verbose.
    if dropped and verbose:
        for line in dropped:
            print(f"note: blanked impossible envelope {line}", file=sys.stderr)

    # Report curated species the archive does not carry under that exact name,
    # so a typo or a renamed synonym is visible instead of silently missing. The
    # full list is behind --verbose because most of them are ornamental species
    # ECOCROP simply never covered, which is expected rather than a defect.
    #
    # Species that lost a name collision are excluded: they are in the archive,
    # just merged into the synonym that carried more envelope data.
    present = {row["scientific_name"] for row in rows}
    if merged and verbose:
        for scientific, name in merged:
            print(
                f"note: merged {scientific} into the row already labelled '{name}'",
                file=sys.stderr,
            )
    merged_species = {scientific for scientific, _ in merged}
    missing = sorted(set(CURATED_NAMES) - present - merged_species)
    if missing:
        if verbose:
            print(
                f"warning: {len(missing)} curated species not found in the archive: "
                f"{', '.join(missing)}",
                file=sys.stderr,
            )
        else:
            print(
                f"note: {len(missing)} curated species are not in the archive "
                f"(run with --verbose to list them)",
                file=sys.stderr,
            )

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build crop_reference.csv from ECOCROP.")
    parser.add_argument("--check", action="store_true",
                        help="regenerate in memory and fail if the committed CSV differs")
    parser.add_argument("--verbose", action="store_true",
                        help="list curated species the archive does not carry")
    args = parser.parse_args()

    archive = fetch_archive()
    taxa, measurements = read_archive(archive)
    rows = build_rows(taxa, measurements, verbose=args.verbose)

    if not rows:
        print("error: no crop rows built - the archive format may have changed", file=sys.stderr)
        return 1

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    generated = buffer.getvalue()

    if args.check:
        existing = OUT_CSV.read_text(encoding="utf-8") if OUT_CSV.exists() else ""
        if existing != generated:
            print("error: crop_reference.csv is stale - run build_crop_data.py", file=sys.stderr)
            return 1
        print(f"ok: {len(rows)} crops, CSV is current")
        return 0

    OUT_CSV.write_text(generated, encoding="utf-8")
    print(f"wrote {OUT_CSV.relative_to(HERE.parent.parent)} - {len(rows)} crops from {SOURCE_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
