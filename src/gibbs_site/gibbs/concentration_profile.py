import logging

class _BaseConcentrationProfile(object):
    
    def Concentration(self, kegg_id):
        raise NotImplementedError


class MolarProfile(_BaseConcentrationProfile):
    
    def Concentration(self, kegg_id):
        return 1.0


class MilliMolarProfile(_BaseConcentrationProfile):
    
    def Concentration(self, kegg_id):
        if kegg_id == 'C00001':
            return 1.0
        return 0.001


class CustomMicroMolarProfile(_BaseConcentrationProfile):
    
    def __init__(self, concentrations):
        self._concentrations = concentrations
        
    def Concentration(self, kegg_id):
        if kegg_id not in self._concentrations:
            logging.error('Concentration requested for unknown id: %s',
                          kegg_id)
        
        return self._concentrations.get(kegg_id, 1000) * 1e-6


_GENERIC_PROFILES = {'1M': MolarProfile(),
                    '1mM': MilliMolarProfile()}


def GetProfile(name='1M',
               all_ids=None,
               all_concentrations=None):
    if name.lower() == 'custom':
        assert all_ids and all_concentrations
        d = dict(zip(all_ids, all_concentrations))
        return CustomMicroMolarProfile(d)
    
    return _GENERIC_PROFILES.get(name, None)