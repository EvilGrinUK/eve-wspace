#    Eve W-Space
#    Copyright (C) 2013  Andrew Austin and other contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version. An additional term under section
#    7 of the GPL is included in the LICENSE file.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from account.models import *

User = get_user_model()

def get_groups_for_code(regcode):
    """Returns a list of groups for a given registration code."""
    grouplist = []
    for group in Group.objects.filter(profile__isnull=False).all():
        profile = GroupProfile.objects.get(group=group)
        if profile.regcode == regcode:
            grouplist.append(group)

    return grouplist

def register_groups(user, regcode):
    """Registers a user for all groups associated with a registration code."""
    grouplist = get_groups_for_code(regcode)
    if len(grouplist) != 0:
        for group in grouplist:
            user.groups.add(group)
    return None
