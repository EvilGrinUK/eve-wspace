from Map.models import *
from Map import utils
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.template.response import TemplateResponse
from django.core.urlresolvers import reverse
from django.template import RequestContext
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from django.conf import settings
from datetime import datetime, timedelta
import pytz
import json

# Decorator to check map permissions. Takes request and mapID
# Permissions are 0 = None, 1 = View, 2 = Change
# When used without a permission=x specification, requires Change access

def require_map_permission(function, permission=2):
    def wrap(request, mapID, *args, **kwargs):
        try:
            map = Map.objects.get(pk=mapID)
            if utils.check_map_permission(reqeust.user, map) < permission:
                raise PermissionDenied
            else:
                return function(*args, **kwargs)
        except DoesNotExist:
            raise Http404

@login_required
def get_map(request, mapID):
    """Get the map and determine if we have permissions to see it. 
    If we do, then return a TemplateResponse for the map. If map does not
    exist, return 404. If we don't have permission, return PermissionDenied.
    """
    try:
        map = Map.objects.get(pk=mapID)
    except DoesNotExist:
        return Http404
    # Check our permissions for the map
    permissions = utils.check_map_permission(request.user, map)
    if permissions == 0:
        return PermissionDenied
    context = utils.get_map_context(map, request.user)
    return TemplateResponse(request, 'map.html', context)

@login_required
def map_checkin(request, mapID):
    # Initialize json return dict
    jsonvalues = {}
    profile = request.user.get_profile()
    # Out AJAX requests should post a JSON datetime called loadtime
    # back that we use to get recent logs.
    if not request.POST.get("loadtime"):
        return HttpResponse(json.dumps({error: "No loadtime"}),mimetype="application/json")
    timestring = request.POST.get("loadtime")
    if request.is_igb:
        loadtime = datetime.strptime(timestring, '%Y-%m-%dT%H:%M:%SZ')
        loadtime = loadtime.replace(tzinfo=pytz.utc)
        if request.is_igb_trusted:
            # Get values to pass in JSON
            oldsystem = ""
            oldsysobj = None
            if profile.currentsystem:
                oldsystem = profile.currentsystem.name
                oldsysobj = System.objects.get(name=oldsystem)
            currentsystem = request.eve_systemname
            currentsysobj = System.objects.get(name=currentsystem)
            # IGB checkin should assert our location
            utils.assert_location(request.user, currentsysobj)
            if profile.lastactive > datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(minutes=5):
                if oldsysobj:
                    if oldsystem != currentsystem and system_is_in_map(oldsysobj, result) == True:
                        if system_is_in_map(currentsysobj, result) == False:
                            dialogHtml = render_to_string('igb_system_add_dialog.html',
                                    {'oldsystem': oldsystem, 'newsystem': currentsystem,
                                        'wormholes': get_possible_wormhole_types(oldsysobj, 
                                        currentsysobj)}, context_instance=RequestContext(request))
                            jsonvalues.update({'dialogHTML': dialogHtml})
    else:
        loadtime = datetime.strptime(timestring, '%Y-%m-%dT%H:%M:%S.%fZ')
        loadtime.replace(tzinfo=pytz.utc)
    newlogquery = MapLog.objects.filter(timestamp__gt=loadtime).all()
    if len(newlogquery) > 0:
        loglist = []
        for log in newlogquery:
            loglist.append("Time: %s  User: %s Action: %s" % (log.timestamp,
                log.user.username, log.action))
        logstring = render_to_string('log_div.html', {'logs': loglist})
        jsonvalues.update({'logs': logstring})
    return HttpResponse(json.dumps(jsonvalues), mimetype="application/json")

def get_system_context(msID):
    try:
        mapsys = MapSystem.objects.get(pk=msID)
        currentmap = mapsys.map

        #if mapsys represents a k-space system get the relevent KSystem object
        if mapsys.system.sysclass > 6:
            system = mapsys.system.ksystem
        #otherwise get the relevant WSystem
        else:
            system = mapsys.system.wsystem
    except ObjectDoesNotExist:
        raise Http404

    scanthreshold = datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(hours=3)
    interestthreshold = datetime.utcnow().replace(tzinfo=pytz.utc) - timedelta(minutes=settings.MAP_INTEREST_TIME)

    scanwarning = system.lastscanned < scanthreshold
    if mapsys.interesttime:
        interest = mapsys.interesttime > interestthreshold
    else:
        interest = False

    return { 'system' : system, 'mapsys' : mapsys, 
             'scanwarning' : scanwarning, 'isinterest' : interest }

    
@login_required
def add_system(request, mapID):
    """
    AJAX view to add a system to a map. Requires POST containing:
       topMsID: MapSystem ID of the parent MapSystem
       bottomSystem: Name of the new system
       topType: WormholeType name of the parent side
       bottomType: WormholeType name of the new side
       timeStatus: Womrhole time status integer value
       massStatus: Wormhole mass status integer value
       topBubbled: 1 if Parent side bubbled
       bottomBubbled: 1 if new side bubbled
       friendlyName: Friendly name for the new MapSystem
    """
    if not request.is_ajax():
       raise PermissionDenied
    try:
        # Prepare data
        map = Map.objects.get(pk=mapID)
        topMS = MapSystem.objects.get(pk=request.POST.get('topMsID'))
        bottomSys = System.objects.get(name=request.POST.get('bottomSystem'))
        topType = WormholeType.objects.get(name=request.POST.get('topType'))
        bottomType = WormholeType.objects.get(name=request.POST.get('bottomType'))
        timeStatus = int(request.POST.get('timeStatus'))
        massStatus = int(request.POST.get('massStatus'))
        topBubbled = "1" == request.POST.get('topBubbled')
        bottomBubbled = "1" == request.POST.get('bottomBubbled')
        # Add System
        bottomMS = utils.add_system_to_map(request.user, map, bottomSys,
                request.POST.get('friendlyName'), False, topMS)
        # Add Wormhole
        add_wormhole_to_map(map, topMS, topType, bottomType, bottomMS,
                bottomBubbled, timeStatus, massStatus, topBubbled)

        return HttpResponse('[]')
    except DoesNotExist:
        return HttpResponse(status=400)


@login_required
def system_details(request, mapID, msID):
    """
    Returns a html div representing details of the System given by msID in
    map mapID
    """
    if not request.is_ajax():
        raise PermissionDenied

    return render(request, 'system_details.html', get_system_context(msID))

@login_required
def system_menu(request, mapID, msID):
    """
    Returns the html for system menu
    """
    if not request.is_ajax():
        raise PermissionDenied

    return render(request, 'system_menu.html', get_system_context(msID))

@login_required
def system_tooltip(request, mapID, msID):
    """
    Returns a system tooltip for msID in mapID
    """
    if not request.is_ajax():
        raise PermissionDenied

    return render(request, 'system_tooltip.html', get_system_context(msID))


@login_required
def wormhole_tooltip(request, mapID, whID):
    """Takes a POST request from AJAX with a Wormhole ID and renders the
    wormhole tooltip for that ID to response.
    
    """
    if request.is_ajax():
        try:
            wh = Wormhole.objects.get(pk=whID)
            return HttpResponse(render_to_string("wormhole_tooltip.html",
                {'wh': wh}, context_instance=RequestContext(request)))
        except ObjectDoesNotExist:
            raise Http404
    else:
        raise PermissionDenied


@login_required()
def mark_scanned(request, mapID, msID):
    """Takes a POST request from AJAX with a system ID and marks that system
    as scanned.

    """
    if request.is_ajax():
        try:
            mapsys = MapSystem.objects.get(pk=msID)
            mapsys.system.lastscanned = datetime.utcnow().replace(tzinfo=pytz.utc)
            mapsys.system.save()
            return HttpResponse('[]')
        except ObjectDoesNotExist:
            raise Http404
    else:
        raise PermissionDenied


@login_required()
def manual_location(request, mapID, msID):
    """Takes a POST request form AJAX with a System ID and marks the user as
    being active in that system.

    """
    if request.is_ajax():
        try:
            mapsystem = MapSystem.objects.get(pk=msID)
            utils.assert_location(request.user, mapsystem.system)
            return HttpResponse("[]")
        except ObjectDoesNotExist:
            raise Http404
    else:
        raise PermissionDenied


@login_required()
def set_interest(request, mapID, msID):
    """Takes a POST request from AJAX with an action and marks that system
    as having either utcnow or None as interesttime. The action can be either 
    "set" or "remove".

    """
    if request.is_ajax():
        action = request.POST.get("action","none")
        if action == "none":
            raise Http404
        try:
            system = MapSystem.objects.get(pk=msID)
            if action == "set":
                system.interesttime = datetime.utcnow().replace(tzinfo=pytz.utc)
                system.save()
                return HttpResponse('[]')
            if action == "remove":
                system.interesttime = None
                system.save()
                return HttpResponse('[]')
            return HttpResponse(staus=418)
        except ObjectDoesNotExist:
            raise Http404
    else:
        raise PermissionDenied

@login_required()
def add_signature(request, mapID, msID):
    """This function processes the Add Signature form. GET gets the form
    and POST submits it and returns either a blank JSON list or a form with errors.
    in addition to the SignatureForm, the form should have a hidden field called sysID
    with the System id. All requests should be AJAX.
    
    """
    if not request.is_ajax():
        raise PermissionDenied
    else:
        if request.method == 'POST':
            form = SignatureForm(request.POST)
            try:
                mapsystem = MapSystem.objects.get(pk=msID)
                if form.is_valid():
                    newSig = form.save(commit=False)
                    newSig.system = mapsystem.system
                    newSig.updated = True
                    newSig.save()
                    return HttpResponse('[]')
                else:
                    return TemplateResponse(request, "add_sig_form.html", {'form': form})
            except DoesNotExist:
                raise Http404
        else:
            form = SignatureForm()
        return TemplateResponse(request, "add_sig_form.html", {'form': form})


@login_required()
def get_signature_list(request, mapID, msID):
    raise PermissionDenied


@login_required
def edit_wormhole(request, whID):
    raise PermissiondDenied


@permission_required('Map.add_Map')
def create_map(request):
    """This function creates a map and then redirects to the new map.

    """
    if request.method == 'POST':
        form = MapForm(request.POST)
        if form.is_valid():
            newMap = form.save()
            add_log(request.user, newMap, "Created the %s map." % (newMap.name))
            add_system_to_map(request.user, newMap, newMap.root, "Root", True, None)
            return HttpResponseRedirect(reverse('Map.views.get_map', 
                kwargs={'mapID': newMap.pk }))
    else:
        form = MapForm
        return TemplateResponse(request, 'new_map.html', { 'form': form, })

