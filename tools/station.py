#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2009 Guillaume Pellerin

# <yomguy@parisson.com>

# This software is a computer program whose purpose is to stream audio
# and video data through icecast2 servers.

# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".

# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited
# liability.

# In this respect, the user's attention is drawn to the risks associated
# with loading, using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.

# Author: Guillaume Pellerin <yomguy@parisson.com>

import os
import time
import datetime
import string
import random
import shout
import tinyurl
from threading import Thread
from __init__ import *

class Station(Thread):
    """a DeeFuzzer shouting station thread"""

    def __init__(self, station, q, logger, m3u):
        Thread.__init__(self)
        self.station = station
        self.q = q
        self.logger = logger
        self.channel = shout.Shout()
        self.id = 999999
        self.counter = 0
        self.command = 'cat '
        self.delay = 0

       # Media
        self.media_dir = self.station['media']['dir']
        self.channel.format = self.station['media']['format']
        self.mode_shuffle = int(self.station['media']['shuffle'])
        self.bitrate = self.station['media']['bitrate']
        self.ogg_quality = self.station['media']['ogg_quality']
        self.samplerate = self.station['media']['samplerate']
        self.voices = self.station['media']['voices']

        # RSS
        self.rss_dir = self.station['rss']['dir']
        self.rss_enclosure = self.station['rss']['enclosure']

        # Infos
        self.channel.url = self.station['infos']['url']
        self.short_name = self.station['infos']['short_name']
        self.channel.name = self.station['infos']['name'] + ' ' + self.channel.url
        self.channel.genre = self.station['infos']['genre']
        self.channel.description = self.station['infos']['description']
        self.base_name = self.rss_dir + os.sep + self.short_name + '_' + self.channel.format
        self.rss_current_file = self.base_name + '_current.xml'
        self.rss_playlist_file = self.base_name + '_playlist.xml'
        self.m3u = m3u

        # Server
        self.channel.protocol = 'http'     # | 'xaudiocast' | 'icy'
        self.channel.host = self.station['server']['host']
        self.channel.port = int(self.station['server']['port'])
        self.channel.user = 'source'
        self.channel.password = self.station['server']['sourcepassword']
        self.channel.mount = '/' + self.short_name + '.' + self.channel.format
        self.channel.public = int(self.station['server']['public'])
        self.channel.audio_info = { 'bitrate': self.bitrate,
                                    'samplerate': self.samplerate,
                                    'quality': self.ogg_quality,
                                    'channels': self.voices,}
        self.playlist = self.get_playlist()
        self.lp = len(self.playlist)
        self.channel.open()
        self.channel_delay = self.channel.delay()

        # Logging
        self.logger.write('Opening ' + self.short_name + ' - ' + self.channel.name + \
                ' (' + str(self.lp) + ' tracks)...')

        self.metadata_relative_dir = 'metadata'
        self.metadata_url = self.channel.url + '/rss/' + self.metadata_relative_dir
        self.metadata_dir = self.rss_dir + os.sep + self.metadata_relative_dir
        if not os.path.exists(self.metadata_dir):
            os.makedirs(self.metadata_dir)

        # The station's player
        self.player = Player()

        # A jingle between each media
        self.jingles_mode = 0
        if 'jingles' in self.station:
            self.jingles_mode =  int(self.station['jingles']['mode'])
            self.jingles_shuffle = self.station['jingles']['shuffle']
            self.jingles_dir = self.station['jingles']['dir']
            if self.jingles_mode == 1:
                self.jingles_callback('/jingles', [1])

        # Relay
        self.relay_mode = 0
        if 'relay' in self.station:
            self.relay_mode = int(self.station['relay']['mode'])
            self.relay_url = self.station['relay']['url']
            if self.relay_mode == 1:
                self.relay_callback('/relay', [1])

        # Twitter
        self.twitter_mode = 0
        if 'twitter' in self.station:
            self.twitter_mode = int(self.station['twitter']['mode'])
            self.twitter_user = self.station['twitter']['user']
            self.twitter_pass = self.station['twitter']['pass']
            self.twitter_tags = self.station['twitter']['tags'].split(' ')
            self.twitter = Twitter(self.twitter_user, self.twitter_pass)
            if self.twitter_mode == 1:
                self.tinyurl = tinyurl.create_one(self.channel.url + '/m3u/' + self.m3u.split(os.sep)[-1])
                self.twitter_callback('/twitter', [1])

        # OSC
        self.osc_control_mode = 0
        if 'control' in self.station:
            self.osc_control_mode = int(self.station['control']['mode'])
            self.osc_port = self.station['control']['port']
            if self.osc_control_mode == 1:
                self.osc_controller = OSCController(self.osc_port)
                self.osc_controller.start()
                # OSC paths and callbacks
                self.osc_controller.add_method('/media/next', 'i', self.media_next_callback)
                self.osc_controller.add_method('/media/relay', 'i', self.relay_callback)
                self.osc_controller.add_method('/twitter', 'i', self.twitter_callback)
                self.osc_controller.add_method('/jingles', 'i', self.jingles_callback)

    def media_next_callback(self, path, value):
        value = value[0]
        self.next_media = value
        message = "Received OSC message '%s' with arguments '%d'" % (path, value)
        self.logger.write(message)

    def relay_callback(self, path, value):
        value = value[0]
        if value == 1:
            self.relay_mode = 1
            self.player.start_relay(self.relay_url)
        elif value == 0:
            self.relay_mode = 0
            self.player.stop_relay()
        self.next_media = 1
        message = "Received OSC message '%s' with arguments '%d'" % (path, value)
        self.logger.write(message)
        message = "Relaying : %s" % self.relay_url
        self.logger.write(message)

    def twitter_callback(self, path, value):
        value = value[0]
        self.twitter_mode = value
        message = "Received OSC message '%s' with arguments '%d'" % (path, value)
        self.logger.write(message)

    def jingles_callback(self, path, value):
        value = value[0]
        if value == 1:
            self.jingles_list = self.get_jingles()
            self.jingles_length = len(self.jingles_list)
            self.jingle_id = 0
        self.jingles_mode = value
        message = "Received OSC message '%s' with arguments '%d'" % (path, value)
        self.logger.write(message)

    def get_playlist(self):
        file_list = []
        for root, dirs, files in os.walk(self.media_dir):
            for file in files:
                s = file.split('.')
                ext = s[len(s)-1]
                if ext.lower() == self.channel.format and not os.sep+'.' in file:
                    file_list.append(root + os.sep + file)
        file_list.sort()
        return file_list

    def get_jingles(self):
        file_list = []
        for root, dirs, files in os.walk(self.jingles_dir):
            for file in files:
                s = file.split('.')
                ext = s[len(s)-1]
                if ext.lower() == self.channel.format and not os.sep+'.' in file:
                    file_list.append(root + os.sep + file)
        file_list.sort()
        return file_list

    def get_next_media(self):
        # Init playlist
        if self.lp != 0:
            old_playlist = self.playlist
            new_playlist = self.get_playlist()
            lp_new = len(new_playlist)

            if lp_new != self.lp or self.counter == 0:
                # Init playlists
                self.playlist = new_playlist
                self.id = 0
                self.lp = lp_new

                # Twitting new tracks
                new_playlist_set = set(self.playlist)
                old_playlist_set = set(old_playlist)
                new_tracks = new_playlist_set - old_playlist_set
                if len(new_tracks) != 0:
                    self.new_tracks = list(new_tracks.copy())
                    new_tracks_objs = self.media_to_objs(self.new_tracks)

                    for media_obj in new_tracks_objs:
                        title = media_obj.metadata['title']
                        artist = media_obj.metadata['artist']
                        if not (title or artist):
                            song = str(media_obj.file_name)
                        else:
                            song = artist + ' : ' + title
                        song = song.encode('utf-8')
                        artist = artist.encode('utf-8')
                        if self.twitter_mode == 1:
                            message = 'New track ! %s #%s #%s' % (song.replace('_', ' '), artist.replace(' ', ''), self.short_name)
                            self.update_twitter(message)

                if self.mode_shuffle == 1:
                    # Shake it, Fuzz it !
                    random.shuffle(self.playlist)

                self.logger.write('Station ' + self.short_name + \
                                 ' : generating new playlist (' + str(self.lp) + ' tracks)')
                self.update_rss(self.media_to_objs(self.playlist), self.rss_playlist_file, '(playlist)')

            if self.jingles_mode == 1 and (self.counter % 2) == 0 and not self.jingles_length == 0:
                media = self.jingles_list[self.jingle_id]
                self.jingle_id = (self.jingle_id + 1) % self.jingles_length
            else:
                media = self.playlist[self.id]
                self.id = (self.id + 1) % self.lp

            return media

        else:
            mess = 'No media in media_dir !'
            self.logger.write(mess)
            sys.exit(mess)

    def media_to_objs(self, media_list):
        media_objs = []
        for media in media_list:
            file_name, file_title, file_ext = get_file_info(media)
            if file_ext.lower() == 'mp3':
                media_objs.append(Mp3(media))
            elif file_ext.lower() == 'ogg':
                media_objs.append(Ogg(media))
        return media_objs

    def update_rss(self, media_list, rss_file, sub_title):
        rss_item_list = []
        if not os.path.exists(self.rss_dir):
            os.makedirs(self.rss_dir)

        channel_subtitle = self.channel.name + ' ' + sub_title
        _date_now = datetime.datetime.now()
        date_now = str(_date_now)
        media_absolute_playtime = _date_now

        for media in media_list:
            media_stats = os.stat(media.media)
            media_date = time.localtime(media_stats[8])
            media_date = time.strftime("%a, %d %b %Y %H:%M:%S +0200", media_date)
            media.metadata['Duration'] = str(media.length).split('.')[0]
            media.metadata['Bitrate'] = str(media.bitrate) + ' kbps'
            media.metadata['Next play'] = str(media_absolute_playtime).split('.')[0]

            media_description = '<table>'
            media_description_item = '<tr><td>%s:   </td><td><b>%s</b></td></tr>'
            for key in media.metadata.keys():
                if media.metadata[key] != '':
                    media_description += media_description_item % (key.capitalize(), media.metadata[key])
            media_description += '</table>'

            title = media.metadata['title']
            artist = media.metadata['artist']
            if not (title or artist):
                song = str(media.file_title)
            else:
                song = artist + ' : ' + title

            media_absolute_playtime += media.length

            if self.rss_enclosure == '1':
                media_link = self.channel.url + '/media/' + media.file_name
                media_link = media_link.decode('utf-8')
                rss_item_list.append(RSSItem(
                    title = song,
                    link = media_link,
                    description = media_description,
                    enclosure = Enclosure(media_link, str(media.size), 'audio/mpeg'),
                    guid = Guid(media_link),
                    pubDate = media_date,)
                    )
            else:
                media_link = self.metadata_url + '/' + media.file_name + '.xml'
                media_link = media_link.decode('utf-8')
                rss_item_list.append(RSSItem(
                    title = song,
                    link = media_link,
                    description = media_description,
                    guid = Guid(media_link),
                    pubDate = media_date,)
                    )

        rss = RSS2(title = channel_subtitle,
                            link = self.channel.url,
                            description = self.channel.description.decode('utf-8'),
                            lastBuildDate = date_now,
                            items = rss_item_list,)

        f = open(rss_file, 'w')
        rss.write_xml(f, 'utf-8')
        f.close()

    def update_twitter(self):
        artist_names = self.artist.split(' ')
        artist_tags = ' #'.join(artist_names)
        message = '♫ %s %s on #%s #%s' % (self.prefix, self.song, self.short_name, artist_tags)
        tags = '#' + ' #'.join(self.twitter_tags)
        message = message + ' ' + tags
        message = message[:113] + ' ' + self.tinyurl
        message = message.decode('utf8')
        self.logger.write('Twitting : "' + message + '"')
        self.twitter.post(message)

    def set_relay_mode(self):
        self.prefix = '#nowplaying (relaying *LIVE*) :'
        song = self.relay_url
        self.song = song.encode('utf-8')
        self.artist = 'Various'
        self.channel.set_metadata({'song': self.short_name + ' relaying : ' + self.song, 'charset': 'utf8',})
        self.stream = self.player.relay_read()

    def set_read_mode(self):
        self.prefix = '#nowplaying :'
        self.current_media_obj = self.media_to_objs([self.media])
        self.title = self.current_media_obj[0].metadata['title']
        self.artist = self.current_media_obj[0].metadata['artist']
        self.title = self.title.replace('_', ' ')
        self.artist = self.artist.replace('_', ' ')
        if not (self.title or self.artist):
            song = str(self.current_media_obj[0].file_name)
        else:
            song = self.artist + ' : ' + self.title
        self.song = song.encode('utf-8')
        self.artist = self.artist.encode('utf-8')
        self.metadata_file = self.metadata_dir + os.sep + self.current_media_obj[0].file_name + '.xml'
        self.update_rss(self.current_media_obj, self.metadata_file, '')
        self.channel.set_metadata({'song': self.song, 'charset': 'utf8',})
        self.update_rss(self.current_media_obj, self.rss_current_file, '(currently playing)')
        self.logger.write('Deefuzzing this file on %s :  id = %s, name = %s' \
            % (self.short_name, self.id, self.current_media_obj[0].file_name))
        self.player.set_media(self.media)
        self.stream = self.player.file_read_slow()

    def run(self):
        while True:
            self.q.get(1)
            self.next_media = 0
            self.media = self.get_next_media()
            self.counter += 1
            self.q.task_done()

            self.q.get(1)
            if self.relay_mode == 1:
                self.set_relay_mode()
            elif os.path.exists(self.media) and not os.sep+'.' in self.media:
                if self.lp == 0:
                    self.logger.write('Error : Station ' + self.short_name + ' has no media to stream !')
                    break
                self.set_read_mode()
            if (not (self.jingles_mode == 1 and (self.counter % 2) == 1) or self.relay_mode == 1) and self.twitter_mode == 1:
                self.update_twitter()
            self.q.task_done()

            for self.chunk in self.stream:
                self.q.get(1)
                try:
                    self.channel.send(self.chunk)
                    self.channel.sync()
                    if self.next_media == 1:
                        break
                except:
                    self.logger.write('ERROR : Station ' + self.short_name + ' : could not send the buffer... ')
                    self.channel.close()
                    self.channel.open()
                    continue
                self.q.task_done()

        self.channel.close()
