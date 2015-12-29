#
# PacketSled - 2015
# Aaron Eppert (aaron.eppert@packetsled.com)
#
# BroControl Configuration Snapshot Interface
#
# Broctl.cfg options:
# snapshot.option = <string> <string> ... -> Paths that should be included in the snapshot - separated by a space
#
#   Example:
#   snapshot.option = /usr/local/bro/lib/bro/plugins /usr/local/bro/etc /usr/local/bro/share/bro
#
# snapshot.dest = "<string>" -> OPTIONAL Path to write the resulting tarball to (${BroBase}/snapshot is the default)
#
# snapshot.exclude = <string> <string> ... -> Entries that should be excluded from inclusion in the snapshot
#

import BroControl.plugin
import os
import sys
import errno
import json
import tarfile
import datetime


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


class SnapshotBro(BroControl.plugin.Plugin):
    snapshot_ext = 'tar.bz2'

    def __init__(self):
        super(SnapshotBro, self).__init__(apiversion=1)

    def name(self):
        return "snapshot"

    def pluginVersion(self):
        return 1

    def init(self):
        self.snapshot_option  = self.getOption("option")
        self.snapshot_dest    = self.getOption("dest")
        self.snapshot_exclude = self.getOption("exclude")
        self.brobase          = self.getGlobalOption("brobase")
        self.snapshotstate    = self.getState("snapshotstate")

        mkdir_p(self.snapshot_dest)

        return True

    def commands(self):
        ret = [("list",       "[-v]",           "List Available Snapshots"),
               ("take",       "[<identifier>]", "Take a Snapshot of the Current Bro Configuration"),
               ("revert",     "<identifier>",   "Revert the Bro Configuration to the Identifier Specified"),
               ("revertfile", "<path>",         "Revert a Snapshot-formatted File"),
               ("remove",     "<identifier>",   "Remove the Snapshot of the Bro Configuration Specified by Identifier")]
        return ret

    def options(self):
        return [("option",  "string", "",                    "Directories or Files to Snapshot"),
                ("dest",    "string", "${BroBase}/snapshot", "Directory to Write Snapshots"),
                ("exclude", "string", "",                    "Entries to exclude from Snapshot"),
                ("ext",     "string", "tar.bz",              "Extension for the Snapshot")]

    def __gen_tarfile_name(self, args):
        ret = args.replace(':', '-')
        ret = ret.replace(' ', '_')
        ret = ret.replace('\?', '_')
        ret = ret.replace('\!', '_')
        ret = '.'.join([ret, SnapshotBro.snapshot_ext])
        return ret

    def __create_tarfile(self, destdir, name, args):
        tar = tarfile.open(os.path.sep.join([destdir, name]), "w:bz2")
        for name in args:
            tar.add(name, exclude=lambda x: any(ex in x for ex in self.__string_to_list(self.snapshot_exclude)))
        tar.close()

    def __extract_tarfile(self, name, basedir='/'):
        tar = tarfile.open(name)
        tar.extractall(path=basedir)
        tar.close()

    def __string_to_list(self, sp_sep_list):
        ret = []
        if len(sp_sep_list) > 0:
            ret = [str(i) for i in sp_sep_list.split()]
        return ret

    def __gen_snapshot_entry(self, state_id, value, ts):
        return {'id': state_id, 'file': value, 'ts': str(ts)}

    def __snapshotstate_get(self):
        ret = {}
        if len(self.snapshotstate) > 0:
            ret = json.loads(self.snapshotstate)
        return ret

    def __snapshotstate_set(self, state):
        self.snapshotstate = json.dumps(state)
        self.setState('snapshotstate', self.snapshotstate)

    def __snapshotstate_entry_id_exist(self, state, identifier):
        ret = False
        if state:
            ret = len([True for x in state if x['id'] == identifier]) > 0
        return ret

    def __snapshotstate_find(self, state_id):
        ret = [x for x in self.__snapshotstate_get() if x['id'] == state_id]
        return ret

    def __snapshotstate_insert(self, state_id, value, ts):
        t_state = self.__snapshotstate_get()

        if t_state:
            if self.__snapshotstate_entry_id_exist(t_state, state_id) == False:
                t_state.append(self.__gen_snapshot_entry(state_id, value, ts))
            else:
                print 'Duplicate identifier "{0}" found - Aborting.'.format(str(state_id))
        else:
            if len(state_id) > 0 and len(value) > 0:
                t_state = []
                t_state.append(self.__gen_snapshot_entry(state_id, value, ts))
            else:
                assert(len(state_id) > 0 and len(value) > 0)

        self.__snapshotstate_set(t_state)

    def __snapshotstate_remove(self, state_id, unlink_file=True):
        t_state = self.__snapshotstate_get()
        if t_state:
            ts = self.__snapshotstate_find(state_id)

            if len(ts) > 0:
                t_file = ts[0]['file']

                try:
                    os.unlink(os.path.sep.join([self.snapshot_dest, t_file]))
                except:
                    pass

                t_state = [x for x in t_state if x['id'] != state_id]
                self.__snapshotstate_set(t_state)

    def _handle_list(self, args):
        t_state = self.__snapshotstate_get()
        if t_state:
            t_state_sorted = sorted(t_state, key=lambda k: k['ts'])

            if '-v' in args:
                print '{0:30s} {1:30s} {2:32s}'.format('IDENTIFIER', 'TIMESTAMP', 'FILE')
                for t in t_state_sorted:
                    print u'{0:30s} {1:30s} {2:32s}'.format(t['id'], t['ts'], t['file'])
            else:
                print '{0:32s} {1:30s}'.format('IDENTIFIER', 'TIMESTAMP')
                for t in t_state_sorted:
                    print '{0:32s} {1:30s}'.format(t['id'], t['ts'])

    def _handle_take(self, args):
        t_list = self.__string_to_list(self.snapshot_option)

        if t_list:
            ts = str(datetime.datetime.utcnow())
            t_id = ts
            if len(args) > 0:
                t_id = str(args)

            t_file = self.__gen_tarfile_name(t_id)
            self.__create_tarfile(self.snapshot_dest,
                                  t_file,
                                  t_list)
            self.__snapshotstate_insert(t_id, t_file, ts)
        else:
            print 'snapshot.option is not configured in broctl.cfg'

    def _handle_revert(self, args):
        if len(args) > 0:
            t_s = self.__snapshotstate_find(args)

            if len(t_s) > 0:
                self.__extract_tarfile(os.path.sep.join([self.snapshot_dest, t_s[0]['file']]))
            else:
                print 'Cannot find snapshot for identifier "{0}"'.format(args)

    def _handle_revertfile(self, args):
        if len(args) > 0:
            if os.path.exists(args):
                self.__extract_tarfile(self, name, basedir='/')

    def _handle_remove(self, args):
        t_state = self.__snapshotstate_get()
        if t_state and len(args) > 0:
                self.__snapshotstate_remove(args)

    def cmd_custom(self, cmd, args, cmdout):
        valid_cmds = {'list':       self._handle_list,
                      'take':       self._handle_take,
                      'revert':     self._handle_revert,
                      'revertfile': self._handle_revertfile,
                      'remove':     self._handle_remove }

        vc = valid_cmds.get(cmd, None)
        assert(vc != None) # Can't be anything else.

        # Run the handler here
        vc(args)
