#!/usr/bin/python

import compound
import approximate_matcher
import reaction_parser
import unittest
import reaction_test_pb2
from google.protobuf import text_format


class TestReactionParser(unittest.TestCase):
    """Tests for matcher.Match"""
    
    input_filename = 'compounds.csv'
    library = compound.ReadCompoundsFromCsvFile(input_filename)
    
    @staticmethod
    def _ReadTestReactions(filename):
        contents = open(filename, 'r').read()
        rxns = reaction_test_pb2.TestReactions()
        text_format.Merge(contents, rxns)
        return rxns
    
    def setUp(self):
        self._matcher = approximate_matcher.BackfillingRegexApproxMatcher(
            self.library, max_results=1, min_score=0.0)
        self._parser = reaction_parser.ReactionParser(self._matcher)
    
    def _CheckReactionSide(self, expected_compounds, actual_compounds):
        """Verifies that a single side of a reaction matches expectations."""
        num_errors = 0
        for expected_compound, actual_compound in zip(expected_compounds, actual_compounds):
            if not actual_compound.ParsedDataEqual(expected_compound):
                print 'Expected to parse as "%d %s"' % (expected_compound.parsed_coeff,
                                                        expected_compound.parsed_name)
                print 'Actually parsed as "%d %s"' % (actual_compound.parsed_coeff,
                                                      actual_compound.parsed_name)
                num_errors += 1
                continue
            
            if len(actual_compound.matches) < len(expected_compound.match_names):
                print 'Expected', len(expected_compound.match_names), 'matches for',
                print expected_compound.parsed_name, 'found', len(actual_compound.matches)
                num_errors += 1
                continue
                                                
            for j, match_name in enumerate(expected_compound.match_names):
                actual_name = str(actual_compound.matches[j].value)
                if match_name != actual_name:
                    print 'Expected name %s does not match actual name %s' % (match_name,
                                                                              actual_name)
                    num_errors += 1
                    continue
        
        return num_errors
                                   
         
    def testAllReactions(self):
        rxns = self._ReadTestReactions('test_reactions.ascii')
        num_reactions = len(rxns.reactions)
        num_reactions_with_errors = 0
        
        
        for i, rxn in enumerate(rxns.reactions):
            print 'Running test reaction', i
            print 'query: ', rxn.query
            
            parsed = self._parser.ParseReactionQuery(rxn.query)
            if not parsed:
                print 'Failed to parse query.'
                num_reactions_with_errors += 1
                continue
                        
            if len(rxn.reactants) != len(parsed.reactants):
                print 'Reactant list lengths are mismatched.'
                num_reactions_with_errors += 1
                continue
            
            if len(rxn.products) != len(parsed.products):
                print 'Product list lengths are mismatched.'
                num_reactions_with_errors += 1
                continue
            
            num_reactant_errors = self._CheckReactionSide(rxn.reactants, parsed.reactants)
            num_product_errors = self._CheckReactionSide(rxn.products, parsed.products)
            if num_reactant_errors:
                print 'Found', num_reactant_errors, 'errors in the reactants list.'
                num_reactions_with_errors += 1
            
            if num_product_errors:
                print 'Found', num_product_errors, 'errors in the products list.'
                num_reactions_with_errors += 1
        
        error_percent = 100.0 * float(num_reactions_with_errors) / float(num_reactions)
        print 'Tested', num_reactions, 'reactions'
        print '%d (%f%%) had errors' % (num_reactions_with_errors, error_percent)

            
   
if __name__ == '__main__':
    unittest.main()