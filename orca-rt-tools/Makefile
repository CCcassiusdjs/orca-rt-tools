all:
	python3.11 -m gcm apps/sample_graph.txt 4 MIN_CPU_USAGE

rgg-exp1:
	python3.11 -m rttools.rgg 10 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/10.txt
	python3.11 -m rttools.rgg 20 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/20.txt
	python3.11 -m rttools.rgg 30 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/30.txt
	python3.11 -m rttools.rgg 40 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/40.txt
	python3.11 -m rttools.rgg 50 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/50.txt
	python3.11 -m rttools.rgg 60 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/60.txt
	python3.11 -m rttools.rgg 70 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/70.txt
	python3.11 -m rttools.rgg 80 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/80.txt
	python3.11 -m rttools.rgg 90 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/90.txt
	python3.11 -m rttools.rgg 100 2000 20000 3 2000 20000 ../apps/experiment-1-nnodes/100.txt

dge-exp1:
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/10.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/20.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/30.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/40.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/50.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/60.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/70.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/80.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/90.txt
	python3.11 -m rttools.gde ../apps/experiment-1-nnodes/100.txt


sgv:
	python3.11 -m gcm apps/var-gdensity/20_001.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_002.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_003.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_004.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_005.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_006.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_007.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_008.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_009.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_010.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_020.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_030.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_040.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_050.txt 4 MIN_COMM
	python3.11 -m gcm apps/var-gdensity/20_060.txt 4 MIN_COMM

# collect random graphs metrics (MIN-COMM)
gde-clustered:
	python3.11 -m gde apps/10_10.clustered.mpmc
	python3.11 -m gde apps/10_20.clustered.mpmc
	python3.11 -m gde apps/10_30.clustered.mpmc
	python3.11 -m gde apps/10_40.clustered.mpmc
	python3.11 -m gde apps/10_50.clustered.mpmc
	python3.11 -m gde apps/10_60.clustered.mpmc
	python3.11 -m gde apps/10_70.clustered.mpmc
	python3.11 -m gde apps/10_80.clustered.mpmc
	python3.11 -m gde apps/10_90.clustered.mpmc
	python3.11 -m gde apps/10_100.clustered.mpmc
	python3.11 -m gde apps/10_200.clustered.mpmc
	python3.11 -m gde apps/10_300.clustered.mpmc
	python3.11 -m gde apps/10_400.clustered.mpmc
	python3.11 -m gde apps/10_500.clustered.mpmc
	python3.11 -m gde apps/10_600.clustered.mpmc
	python3.11 -m gde apps/10_700.clustered.mpmc
	python3.11 -m gde apps/10_800.clustered.mpmc
	python3.11 -m gde apps/10_900.clustered.mpmc
	python3.11 -m gde apps/10_1000.clustered.mpmc

clean:
	rm -rf apps/*.dot apps/*.clustered apps/*.png apps/*.trace* apps/*.svg


# FORMAT:
format:
	echo "python3.11 rttools/__main__.py <app> <map> <arch> [<freq>] [<step>] [<tries>]"

# SHI et al. 2010
shi:
	python3.11 rttools/__main__.py application/SHI2010.csv mappings/SHI2010-ONTO-hermes4x4.map architecture/hermes-4x4.gml 2000000 2000 500

# simple-graph app
simple-graph-b:
	python3.11 -m rttools ../apps/experiment-1-nnodes/sample-graph-b/sample-graph-b.csv  ../apps/experiment-1-nnodes/sample-graph-b/hermes2x2.map ../arch/hermes-2x2.gml 1000000 1 2000 False
	firefox ../apps/experiment-1-nnodes/sample-graph-b/results.svg





.PHONY: all rgg clean rgg_gen gde gde-min-comm gcm