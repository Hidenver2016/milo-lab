from os import path
import json
import logging
from django.shortcuts import render_to_response
from django.http import HttpResponse
from django.http import Http404
from gibbs import compound_form
from gibbs import form_utils
from gibbs import models
from gibbs import reaction_form
from gibbs import search_form
from gibbs import service_config
from group_contribution import compound_estimate
from group_contribution import constants
from matching import approximate_matcher
from matching import compound
from matching import reaction_parser

THERMO_FILE_PATH = path.abspath("group_contribution/kegg_thermo_data.csv")
COMPOUND_ESTIMATES = compound_estimate.CompoundEstimates.FromCsvFile(THERMO_FILE_PATH)
    

def MainPage(request):
    """Renders the landing page."""
    return render_to_response('main.html', {})


def SuggestJson(request):
    """Renders the suggest JSON."""
    form = search_form.SearchForm(request.GET)
    if not form.is_valid():
        logging.error(form.errors)
        raise Http404
    
    matcher = service_config.Get().compound_matcher
    query = str(form.cleaned_query)
    results = [unicode(m.key) for m in matcher.Match(query)]
    json_data = json.dumps({'query': query, 'suggestions': results})
    
    return HttpResponse(json_data, mimetype='application/json')


def CompoundPage(request):
    """Renders a page for a particular compound."""
    form = compound_form.CompoundForm(request.GET)
    if not form.is_valid():
        logging.error(form.errors)
        raise Http404
    
    # Compute the delta G estimate.
    kegg_id = form.cleaned_compoundId
    compound = models.Compound.objects.get(kegg_id=kegg_id)
    delta_g_estimate = compound.GetFormationEnergy(
        pH=form.cleaned_ph, ionic_strength=form.cleaned_ionic_strength, 
        temp=form.cleaned_temp)
    
    template_data = {'compound': compound, 
                     'temp': form.cleaned_temp,
                     'ph': form.cleaned_ph,
                     'ionic_strength': form.cleaned_ionic_strength,
                     'delta_g_estimate': delta_g_estimate,
                     'kegg_link': compound.GetKeggLink()}
    return render_to_response('compound_page.html', template_data)


def ReactionPage(request):
    """Renders a page for a particular reaction."""
    form = reaction_form.ReactionForm(request.GET)
    if not form.is_valid():
        logging.error(form.errors)
        raise Http404
    
    
    clean_reactants = form.cleaned_reactantIds
    clean_products = form.cleaned_productIds
    zipped_reactants = zip(form.cleaned_reactantCoeffs, clean_reactants)
    zipped_products = zip(form.cleaned_productCoeffs, clean_products)

    # Compute the delta G estimate.
    temp = form.cleaned_temp
    i_s = form.cleaned_ionic_strength
    ph = form.cleaned_ph
    delta_g_estimate = None
    warning = None
    delta_g_estimate = models.Compound.GetReactionEnergy(
        zipped_reactants, zipped_products, pH=ph,
        ionic_strength=i_s, temp=temp)
    if not models.Compound.ReactionIsBalanced(zipped_reactants, zipped_products):
        warning = 'Reaction is not balanced!'

    # Make sure that we can parse the reaction.
    # TODO(flamholz): Use the compound name the user selected, rather than the first one.
    reactants = models.Compound.GetCompoundsByKeggId(clean_reactants)
    products = models.Compound.GetCompoundsByKeggId(clean_products)
    rdicts, pdicts = [], []
    
    params = 'temp=%f&ph=%f&ionic_strength=%f' % (temp, ph, i_s)
    get_compound_link = lambda c: '/compound?compoundId=%s&%s' % (c.kegg_id, params)
    for coeff, id in zip(form.cleaned_reactantCoeffs, clean_reactants):
        compound = reactants[id]
        rdicts.append({'coeff': coeff, 'compound': compound,
                       'compound_link': get_compound_link(compound)})
    for coeff, id in zip(form.cleaned_productCoeffs, clean_products):
        compound = products[id]
        pdicts.append({'coeff': coeff, 'compound': compound,
                       'compound_link': get_compound_link(compound)})
    
    rxn = {'products': pdicts,
           'reactants': rdicts}
    
    template_data = {'reaction': rxn, 
                     'temp': form.cleaned_temp,
                     'ph': form.cleaned_ph,
                     'ionic_strength': form.cleaned_ionic_strength,
                     'delta_g_estimate': delta_g_estimate,
                     'warning': warning}
    return render_to_response('reaction_page.html', template_data)

    
def ResultsPage(request):
    """Renders the search results page for a given query."""
    form = search_form.SearchForm(request.GET)
    if not form.is_valid():
        raise Http404
    
    reaction_parser = service_config.Get().reaction_parser
    matcher = service_config.Get().compound_matcher
    
    query = str(form.cleaned_query)
    temp = form.cleaned_temp
    ph = form.cleaned_ph
    ionic_strength = form.cleaned_ionic_strength
    template_data = {'query': query,
                     'temp': temp,
                     'ph': ph,
                     'ionic_strength': ionic_strength}
    
    # Check if we should parse and process the input as a reaction.
    if reaction_parser.ShouldParseAsReaction(query):
        parsed_reaction = reaction_parser.ParseReactionQuery(query)
        delta_g_estimate = None
        best_reaction = parsed_reaction.GetBestMatch()
        if best_reaction:
            reactants, products = best_reaction
            delta_g_estimate = models.Compound.GetReactionEnergy(
                reactants, products, pH=ph,
                ionic_strength=ionic_strength, temp=temp)
            if not models.Compound.ReactionIsBalanced(reactants, products):
                if models.Compound.CanBalanceReactionWithWater(reactants, products):
                    template_data['warning'] = 'Reaction is not balanced! Balance with water?'
                else:
                    template_data['warning'] = 'Reaction is not balanced!'
            
        template_data['delta_g_estimate'] = delta_g_estimate
        template_data['parsed_reaction'] = parsed_reaction
        return render_to_response('reaction_result.html',
                                  template_data)

    else:
        # Otherwise we try to parse it as a single compound.
        results = matcher.Match(query)
        delta_g_estimate = None
        compound = results[0].value
        if results:
            delta_g_estimate = compound.GetFormationEnergy(
                pH=ph, ionic_strength=ionic_strength, temp=temp)
        
        template_data['kegg_link'] = results[0].value.GetKeggLink()
        template_data['results'] = results
        template_data['delta_g_estimate'] = delta_g_estimate
        return render_to_response('compound_result.html',
                                  template_data)

    raise Http404