import csv, re
from pylab import NaN, isfinite
from thermodynamics import Thermodynamics, MissingCompoundFormationEnergy
from pygibbs import pseudoisomer
from toolbox.database import SqliteDatabase

class Alberty(Thermodynamics):
    def read_alberty_mathematica(self, fname):
        """
            example line:
            acetatesp={{-369.31,-486.01,-1,3},{-396.45,-485.76,0,4}};
            
            the order of values is: (dG0, dH0, z, nH)
        """
        fp = open(fname, 'r')
        alberty_name_to_pmap = {}
        alberty_name_to_hmap = {} # same as pmap but for dH of formation
        for line in fp.readlines():
            line.rstrip()
            if line.find('=') == -1:
                continue
            (alberty_name, values) = line.split('sp=', 1)
            for token in re.findall("{([0-9\-\.\,_\s]+)}", values):
                val_list = token.split(',', 3)
                if len(val_list) != 4:
                    raise ValueError("Syntax error at: " + line)
                dG0 = float(val_list[0])
                try:
                    dH0 = float(val_list[1])
                except ValueError:
                    dH0 = NaN
                z = int(val_list[2])
                nH = int(val_list[3])
                if alberty_name.find("coA") != -1:
                    nH += 32
                nMg = 0
                
                alberty_name_to_pmap.setdefault(alberty_name, pseudoisomer.PseudoisomerMap())
                alberty_name_to_pmap[alberty_name].Add(nH, z, nMg, dG0, 
                                                       ref='Alberty 2006')
                if isfinite(dH0):
                    alberty_name_to_hmap.setdefault(alberty_name, pseudoisomer.PseudoisomerMap())
                    alberty_name_to_hmap[alberty_name].Add(nH, z, nMg, dH0, 
                                                           ref='Alberty 2006')
            
        return alberty_name_to_pmap, alberty_name_to_hmap
        
    def read_alberty_kegg_mapping(self, fname):
        alberty_name_to_cid = {}
        csv_file = csv.reader(open(fname, 'r'))
        csv_file.next()
        for row in csv_file:
            if row[0] and row[2]:
                alberty_name_to_cid[row[2]] = int(row[0])
        return alberty_name_to_cid
    
    def __init__(self):
        Thermodynamics.__init__(self)
        alberty_name_to_pmap, alberty_name_to_hmap = \
            self.read_alberty_mathematica("../data/thermodynamics/alberty_mathematica_fixed.txt")
        alberty_name_to_cid = \
            self.read_alberty_kegg_mapping("../data/thermodynamics/alberty_names.csv")

        self.cid2pmap_dict = {}
        self.cid2hmap_dict = {}
        for name in sorted(alberty_name_to_cid.keys()):
            cid = alberty_name_to_cid[name]
            self.cid2source_string[cid] = 'Alberty (2006)'
            if name in alberty_name_to_pmap:
                self.cid2pmap_dict[cid] = alberty_name_to_pmap[name]
            if name in alberty_name_to_hmap:
                self.cid2hmap_dict[cid] = alberty_name_to_hmap[name]
    
    def cid2PseudoisomerMap(self, cid):
        try:
            return self.cid2pmap_dict[cid]
        except KeyError:
            raise MissingCompoundFormationEnergy("The compound C%05d does not have a value for its formation energy of any of its pseudoisomers" % cid, cid)

    def get_all_cids(self):
        return sorted(self.cid2pmap_dict.keys())
    
if __name__ == '__main__':
    A = Alberty()
    db_public = SqliteDatabase('../data/public_data.sqlite')
    A.ToDatabase(db_public, 'alberty_pseudoisomers')