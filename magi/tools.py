# -*- coding: utf-8 -*-
import datetime, time, sys, os, math, pytz
from PIL import Image
from django.utils import timezone
from django.utils.translation import activate as translation_activate, ugettext_lazy as _, get_language
from django.utils.formats import date_format
from django.utils.html import escape
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings as django_settings
from django.db.models import Count
from magi.utils import (
    birthdays_within,
    getMagiCollections,
    imageSquareThumbnailFromData,
    imageURLToImageFile,
    makeImageGrid,
    saveLocalImageToModel,
    getEventStatus,
    create_user as utils_create_user,
    get_default_owner as utils_get_default_owner,
)
from magi.settings import (
    SITE_STATIC_URL,
    STATIC_FILES_VERSION,
    SEASONS,
)
from magi import models, seasons

############################################################
# Create user

def create_user(*args, **kwargs):
    return utils_create_user(models.User, *args, **kwargs)

def get_default_owner(*args, **kwargs):
    return utils_get_default_owner(models.User, *args, **kwargs)

############################################################
# Get user from link

def getUserFromLink(value, type=None):
    if type:
        try:
            return models.UserLink.objects.select_related('owner', 'owner__preferences').filter(
                i_type=models.UserLink.get_i('type', type), value__iexact=value)[0].owner
        except IndexError:
            return None
    try:
        return models.User.objects.select_related('preferences').filter(links__value__iexact=value)[0]
    except IndexError:
        return None

############################################################
# Get total donators (for generated settings)

def totalDonatorsThisMonth():
    now = timezone.now()
    this_month = datetime.datetime(year=now.year, month=now.month, day=1)
    try:
        donation_month = models.DonationMonth.objects.get(date=this_month)
    except ObjectDoesNotExist:
        try:
            donation_month = models.DonationMonth.objects.order_by('-date')[0]
        except IndexError:
            return 0
    return models.Badge.objects.filter(donation_month=donation_month).values('user').distinct().count()

def totalDonators():
    return models.UserPreferences.objects.filter(i_status__isnull=False).exclude(i_status__exact='').count()

############################################################
# Get latest donation month (for generated settings)

def latestDonationMonth(failsafe=False):
    now = timezone.now()
    this_month = datetime.datetime(year=now.year, month=now.month, day=1)
    try:
        donation_month = models.DonationMonth.objects.get(date=this_month)
    except ObjectDoesNotExist:
        if not failsafe:
            return None
        try:
            donation_month = models.DonationMonth.objects.order_by('-date')[0]
        except IndexError:
            donation_month = None
    if not donation_month:
        return {
            'percent': 0,
            'percent_int': 0,
            'date': this_month,
            'donations': 0,
            'reached_100_percent': False,
        }
    return {
        'percent': donation_month.percent,
        'percent_int': donation_month.percent_int,
        'date': donation_month.date,
        'donations': donation_month.donations,
        'reached_100_percent': donation_month.reached_100_percent,
    }

############################################################
# Get staff configurations (for generated settings)

def getStaffConfigurations():
    staff_configurations = {}
    latest_news = { i: {} for i in range(1, 5) }
    for staffconfiguration in models.StaffConfiguration.objects.all():
        if staffconfiguration.value is None or staffconfiguration.value == '':
            continue
        if staffconfiguration.key.startswith('banner_'):
            latest_news[int(staffconfiguration.key.split('_')[1])]['_'.join(staffconfiguration.key.split('_')[2:])] = staffconfiguration.boolean_value
            continue
        if staffconfiguration.i_language:
            if staffconfiguration.key not in staff_configurations:
                staff_configurations[staffconfiguration.key] = {}
            staff_configurations[staffconfiguration.key][staffconfiguration.language] = staffconfiguration.value
        else:
            staff_configurations[staffconfiguration.key] = staffconfiguration.value
    return staff_configurations, [
        latest_news[i] for i in range(1, 5)
        if latest_news[i] and latest_news[i].get('image') and latest_news[i].get('title') and latest_news[i].get('url') ]

############################################################
# Get characters birthdays (for generated settings)

def getCharactersBirthdays(queryset, get_name_image_url_from_character,
                           latest_news=None, days_after=12, days_before=1, field_name='birthday'):
    if not latest_news:
        latest_news = []
    now = timezone.now()
    characters = list(queryset.filter(
        birthdays_within(days_after=days_after, days_before=days_before, field_name=field_name)
    ).order_by('name'))
    characters.sort(key=lambda c: getattr(c, field_name).replace(year=2000))
    for character in characters:
        name, image, url = get_name_image_url_from_character(character)
        if name is None or image is None:
            continue
        t_titles = {}
        old_lang = get_language()
        for lang, _verbose in django_settings.LANGUAGES:
            translation_activate(lang)
            t_titles[lang] = u'{}, {}! {}'.format(
                _('Happy Birthday'),
                name,
                date_format(getattr(character, field_name), format='MONTH_DAY_FORMAT', use_l10n=True),
            )
        translation_activate(old_lang)
        latest_news.append({
            't_titles': t_titles,
            'background': image,
            'url': url,
            'hide_title': False,
            'ajax': False,
            'css_classes': 'birthday',
        })
    return latest_news

############################################################
# Get users birthdays (for generated settings)

def getUsersBirthdaysToday(image, latest_news=None, max_usernames=4):
    if not latest_news:
        latest_news = []
    now = timezone.now()
    users = list(models.User.objects.filter(
        preferences__birthdate__day=now.day,
        preferences__birthdate__month=now.month,
    ).order_by('-preferences___cache_reputation'))
    if users:
        usernames = u'{}{}'.format(
            u', '.join([user.username for user in users[:max_usernames]]),
            u' + {}'.format(len(users[max_usernames:])) if users[max_usernames:] else '',
        )
        t_titles = {}
        old_lang = get_language()
        for lang, _verbose in django_settings.LANGUAGES:
            translation_activate(lang)
            t_titles[lang] = u'{} 🎂🎉 {}'.format(
                _('Happy Birthday'),
                usernames,
            )
        translation_activate(old_lang)
        latest_news.append({
            't_titles': t_titles,
            'image': image,
            'url': (
                users[0].item_url
                if len(users) == 1
                else u'/users/?ids={}&ordering=preferences___cache_reputation&reverse_order=on'.format(u','.join([unicode(user.id) for user in users]))
            ),
            'hide_title': False,
            'css_classes': 'birthday font0-5',
        })
    return latest_news

############################################################
# Generate share images for list views

# Can be changed:
IMAGES_PER_SHARE_IMAGE = 9
SHARE_IMAGE_PER_LINE = 3
SHARE_IMAGES_SIZE = 200

def generateShareImageForMainCollections(collection):
    # Get queryset to get items in list view
    try:
        queryset = collection.list_view.get_queryset(collection.queryset, {}, None)
    except:
        queryset = collection.queryset
    queryset = queryset.order_by(*collection.list_view.default_ordering.split(','))[:100]
    # Get images for each item
    images = []
    for item in queryset:
        for field_name in ['share_image_in_list', 'share_image', 'top_image_list', 'top_image', 'image']:
            image = getattr(item, field_name, None)
            if image:
                images.append(image)
                break
        if len(images) == IMAGES_PER_SHARE_IMAGE:
            break
    if len(images) != IMAGES_PER_SHARE_IMAGE:
        print '!! Warning: Not enough images to generate share image for', collection.plural_name
        return None
    # Create share image from images
    return unicode(makeImageGrid(
        images,
        per_line=SHARE_IMAGE_PER_LINE,
        size_per_tile=SHARE_IMAGES_SIZE,
        upload=True,
        model=models.UserImage,
        previous_url=getattr(django_settings, 'GENERATED_SHARE_IMAGES', {}).get(collection.name, None),
    ).image)

############################################################
# Generate settings (for generated settings)

def magiCirclesGeneratedSettings(existing_values):
    now = timezone.now()
    one_week_ago = now - datetime.timedelta(days=10)

    # Get staff configurations if missing
    staff_configurations = existing_values.get('STAFF_CONFIGURATIONS', None)
    latest_news = existing_values.get('LATEST_NEWS', [])

    if not staff_configurations:
        staff_configurations, more_latest_news = getStaffConfigurations()
        latest_news += more_latest_news

    # Generate share images once a week
    if django_settings.DEBUG:
        generated_share_images_last_date = now
        generated_share_images = {}
    else:
        generated_share_images_last_date = getattr(django_settings, 'GENERATED_SHARE_IMAGES_LAST_DATE', None)
        if (generated_share_images_last_date
            and generated_share_images_last_date.replace(tzinfo=pytz.utc) > one_week_ago):
            generated_share_images = getattr(django_settings, 'GENERATED_SHARE_IMAGES', {})
        else:
            generated_share_images_last_date = now
            generated_share_images = {}
            print 'Generate auto share images'
            for collection_name, collection in getMagiCollections().items():
                if collection.auto_share_image:
                    generated_share_images[collection.name] = generateShareImageForMainCollections(collection)

    seasonal_settings = {}

    # Set seasonal settings
    for season_name, season in SEASONS.items():
        if getEventStatus(season['start_date'], season['end_date'], ends_within=1) in ['current', 'ended_recently']:
            seasonal_settings[season_name] = {}
            for variable in seasons.AVAILABLE_SETTINGS:
                if variable in season:
                    seasonal_settings[season_name][variable] = season[variable]
            for variable in seasons.STAFF_CONFIGURATIONS_SETTINGS + season.get('staff_configurations_settings', []):
                value = staff_configurations.get(u'season_{}_{}'.format(season_name, variable), None)
                if value is not None:
                    seasonal_settings[season_name][variable] = value

    return {
        'STAFF_CONFIGURATIONS': staff_configurations,
        'LATEST_NEWS': latest_news,
        'GENERATED_SHARE_IMAGES_LAST_DATE': 'datetime.datetime.fromtimestamp(' + unicode(
            time.mktime(generated_share_images_last_date.timetuple())
        ) + ')',
        'GENERATED_SHARE_IMAGES': generated_share_images,
        'SEASONAL_SETTINGS': seasonal_settings,
    }, []

def generateSettings(values, imports=[]):
    m_values, m_imports = magiCirclesGeneratedSettings(values)
    m_values.update(values)
    imports = m_imports + imports
    s = u'\
# -*- coding: utf-8 -*-\n\
import datetime\n\
' + u'\n'.join(imports) + '\n\
' + u'\n'.join([
    u'{key} = {value}'.format(key=key, value=unicode(value))
    for key, value in m_values.items()
]) + '\n\
GENERATED_DATE = datetime.datetime.fromtimestamp(' + unicode(time.time()) + u')\n\
'
    print s
    with open(django_settings.BASE_DIR + '/' + django_settings.SITE + '_project/generated_settings.py', 'w') as f:
        f.write(s.encode('utf8'))
        f.close()

############################################################
# Generate map

def generateMap():
    print '[Info]', datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 'Generating map...'
    map = models.UserPreferences.objects.filter(latitude__isnull=False).select_related('user')

    mapcache = u'{# this file is generated, do not edit it #}{% extends "base.html" %}{% load l10n %}{% block content %}<div class="padding15" id="map-title">{% include \'include/page_title.html\' with show_small_title=True %}</div><div id="map"></div>{% endblock %}{% block afterjs %}{% localize off %}<script>var center=new google.maps.LatLng({% if center %}{{ center.latitude }},{{ center.longitude }}{% else %}30,0{% endif %});var zoom={% if zoom %}{{ zoom }}{% else %}2{% endif %};var addresses = ['

    for u in map:
        try:
            mapcache += u'{open}"user_id": {user_id}, "username": "{username}","avatar": "{avatar}","location": "{location}","icon": "{icon}","latlong": new google.maps.LatLng({latitude},{longitude}){close},'.format(
                open=u'{',
                user_id=u.user_id,
                username=escape(u.user.username),
                avatar=escape(models.avatar(u.user)),
                location=escape(u.location),
                icon=escape(u.favorite_character1_image if u.favorite_character1_image else SITE_STATIC_URL + u'static/img/default_map_icon.png'),
                latitude=u.latitude,
                longitude=u.longitude,
                close=u'}',
            )
        except:
            print 'One user not added in map', u.user.username, u.location
            print sys.exc_info()[0]

    mapcache += u'];</script><script src="' + SITE_STATIC_URL + u'static/js/map.js?' + STATIC_FILES_VERSION + u'"></script>{% endlocalize %}{% endblock %}'

    with open(django_settings.BASE_DIR + '/' + django_settings.SITE + '/templates/pages/map.html', 'w') as f:
        f.write(mapcache.encode('UTF-8'))
    f.close()
    print '[Info]', datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 'Done'
