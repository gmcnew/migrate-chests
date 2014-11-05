import argparse
import codecs
import math
import os
import re
import shutil
import sys

from datetime import *
from pymclevel import mclevel, mclevelbase, nbt

KEY_CHESTS      = 'Chests'
KEY_SIGNS       = 'Signs'
RAW_DATA_FILE   = 'raw_items.nbt'
SEARCH_LIMIT    = 17
LABEL_PATTERN   = re.compile("\S+:\S+")
SIGN_TEXT_KEYS  = ["Text%d" % (i + 1) for i in range(4)]
CHEST_TYPES     = set(['Chest', 'Dropper', 'Furnace', 'Hopper', 'Trap'])

def loc(entity):
    return tuple(int(entity[c].value) for c in ['x', 'y', 'z'])

def plural(count, string, invert = False):
    suffix = "" if ((count == 1) ^ invert) else "s"
    return "%d %s%s" % (count, string, suffix)

def exit_if_file_exists(filename, string):
    if os.path.exists(filename):
        sys.exit("%s file '%s' already exists." % (
            string, filename))

class Progress:
    def __init__(self, n):
        self.last_percent = -1
        self.n = n
        self.start_time = None
        self.etas = []
        self.eta_index = 0
        self.last_write_len = 0
        self.precision = 1000

    def __str__(self):
        dt = datetime.now() - self.start_time
        p = float(self.percent) / self.precision
        retval = ("%.1f%%" if p < 1 else "%.0f%%") % (p * 100)
        SAMPS = 100
        if dt.seconds >= 3 and p > 0:
            eta = dt.seconds * (1.0 - p) / p
            if len(self.etas) < SAMPS:
                self.etas.append(eta)
            self.etas[self.eta_index] = eta
            self.eta_index = (self.eta_index + 1) % SAMPS

            samples = self.etas#sorted(self.etas)[1:-1]
            if len(samples) >= SAMPS and p < 1:
                eta = sum(samples) / float(len(samples))
                retval += ", "
                if eta > 60:
                    mins = int(eta / 60)
                    eta -= mins * 60
                    retval += "%d min " % mins
                retval += "%d sec left" % eta
        return retval

    def tick(self, i, desc):
        if self.start_time is None:
            self.start_time = datetime.now()
        self.percent = i * self.precision / self.n
        if self.percent != self.last_percent:
            self.last_percent = self.percent
            toWrite = "%s (%s)..." % (desc, self)
            sys.stdout.write("\r" + toWrite
                + " " * (self.last_write_len - len(toWrite)))
            self.last_write_len = len(toWrite)
            sys.stdout.flush()

    def __del__(self):
        if self.start_time is not None:
            print("")

def get_migration_label(sign):
    for key in SIGN_TEXT_KEYS:
        text = sign[key].value.strip().strip('"')
        if text and LABEL_PATTERN.match(text):
            return text.lower()
    return None

def label_chests(labelItems, chests_c, signs_c, closest_only):
    markers = []
    for sign_c in signs_c:
        label = get_migration_label(sign_c[0])
        if label:
            markers.append((loc(sign_c[0]), label))
            if label not in labelItems:
                labelItems[label] = { KEY_CHESTS: [], KEY_SIGNS: [] }
            labelItems[label][KEY_SIGNS].append(sign_c)

    def chest_to_coords(chest, coords):
        dist = 0
        for (a, b) in zip(loc(chest), coords):
            dist += abs(a - b)
        return dist

    print("Matching %s with %s..." % (
        plural(len(chests_c), "chest"),
        plural(len(markers), "migration sign")))

    numOrphans = 0
    for chest_c in chests_c:
        bestDist = SEARCH_LIMIT + 1
        labels = []
        for (coords, label) in markers:
            dist = chest_to_coords(chest_c[0], coords)
            if dist < bestDist:
                if closest_only:
                    bestDist = dist
                    labels = [label]
                else:
                    labels.append(label)

        if labels:
            for label in labels:
                labelItems[label][KEY_CHESTS].append(chest_c)
        else:
            numOrphans += 1

    return len(chests_c) - numOrphans

def copy_from(paths):
    exit_if_file_exists(RAW_DATA_FILE, "Data")

    print("Chests and signs in %s will be prepared for migration." % plural(len(paths), "world"))

    n = len(paths)
    labelItems = {}
    for (i, path) in enumerate(paths):
        print("\nLoading source world %d of %d (%s)..." % (i + 1, n, path))
        level = mclevel.fromFile(path)
        (numChunks, chests_c, signs_c) = copy_from_single(level)
        chestsToMigrate = label_chests(labelItems, chests_c, signs_c, closest_only = True)
        print("%s will be migrated." % plural(chestsToMigrate, "chest"))
         
    print("\nSaving results...")
    allData = nbt.TAG_Compound()
    for label in labelItems:
        allItems = []
        for x in labelItems[label][KEY_CHESTS]:
            allItems.extend(x[0]['Items'])
        if len(allItems) > 0:
            allData[label] = nbt.TAG_List(allItems)
    allData.save(RAW_DATA_FILE)
    print("Finished.")

def copy_from_single(level):
    chunks = list(level.allChunks)
    (chests_c, signs_c) = find_chests_and_signs(level, chunks)
    return (len(chunks), chests_c, signs_c)

def find_chests_and_signs(level, chunks):
    progress = Progress(len(chunks))
    chests_c = []
    signs_c = []
    malformedChunks = 0
    for i, cPos in enumerate(chunks):
        progress.tick(i + 1, "Examining chunks")

        try:
            chunk = level.getChunk(*cPos)
        except mclevelbase.ChunkMalformed:
            malformedChunks += 1
            continue
        
        for ent in chunk.TileEntities:
            idVal = ent['id'].value
            if idVal in CHEST_TYPES:
                chests_c.append((ent, i))
            elif idVal == 'Sign' and get_migration_label(ent):
                signs_c.append((ent, i))

    if malformedChunks:
        del progress
        print("Skipped %s" % plural(malformedChunks, "malformed chunk")) 

    return (chests_c, signs_c)

# Change a line on a sign to "(migrated!)".
# Choose the first line following a non-blank line.
# If there are no such lines, choose the last blank line.
# If there are no blank lines, choose the last line.
def mark_sign_as_migrated(sign, chunk):
    changeKey = SIGN_TEXT_KEYS[-1]
    textFound = False
    for key in SIGN_TEXT_KEYS:
        text = sign[key].value.strip().strip('"')
        if text:
            textFound = True
        else:
            changeKey = key
            if textFound:
                break
    sign[changeKey].value = "(migrated!)"
    chunk.chunkChanged()

def mark_signs_c_as_migrated(level, chunks, signs_c):
    for (sign, c) in signs_c:
        (cx, cz) = chunks[c]
        chunk = level.getChunk(cx, cz)
        signLoc = loc(sign)
        for i in range(len(chunk.TileEntities)):
            ent = chunk.TileEntities[i]
            if loc(ent) == signLoc:
                mark_sign_as_migrated(ent, chunk)
                break

def migrate_into_chest(chunk, chest, itemsLeft):
    migrated = 0
    for i in range(len(chunk.TileEntities)):
        if not itemsLeft:
            break
        entPos = loc(chunk.TileEntities[i])

        freeSlots = []
        if entPos == loc(chest):
            chest = chunk.TileEntities[i]
            usedSlots = set()
            for item in chest['Items']:
                usedSlots.add(item['Slot'].value)
            freeSlots = set(range(27)).difference(usedSlots)
            freeSlots = sorted(list(freeSlots), key = lambda x: -x)

        if not freeSlots:
            continue

        while itemsLeft and freeSlots:
            item = itemsLeft.pop()
            slot = freeSlots.pop()
            item['Slot'].value = slot

            # Convert stone wooden slabs to oak wooden slabs.
            if item['id'].value == 44:
                if item['Damage'].value == 2:
                    item['id'].value = 126
                    item['Damage'].value = 0
            
            # Remove no-decay flags from leaves.
            elif item['id'].value in [18, 161]:
                if item['Damage'].value >= 4:
                    item['Damage'].value %= 4

            # Fix sticky pistons.
            elif item['id'].value == 29:
                item['Damage'].value = 0

            chest['Items'].append(item)
            migrated += 1

        chunk.chunkChanged()

    return migrated


def load_migration_data():
    print("Loading migration data...")
    data = nbt.load(RAW_DATA_FILE)
    fromItems = {}
    for (key, val) in data.items():
        fromItems[key] = val
    return fromItems

def print_remaining_items():
    fromItems = load_migration_data()
    total = 0
    for key in sorted(fromItems):
        remaining = len(fromItems[key])
        print("%4d slots for %s" % (remaining, key))
        total += remaining
    print("%4d total" % total)

def migrate_to(path):
    fromItems = load_migration_data()
    
    print("Loading destination world...")
    level = mclevel.fromFile(path)
    chunks = list(level.allChunks)

    (chests_c, signs_c) = find_chests_and_signs(level, chunks)

    print("Found %s and %s.\n" % (
        plural(len(chests_c), "chest"),
        plural(len(signs_c), "sign")))

    toItems = {}
    label_chests(toItems, chests_c, signs_c, closest_only = False)

    fromLabels = set()
    toLabels   = set(list(toItems.keys()))
    for (label, items) in fromItems.items():
        if items:
            fromLabels.add(label)

    totalMigrated = 0

    # Merge!
    for label in fromLabels.intersection(toLabels):
        sys.stdout.write(label)
        itemsLeft = fromItems[label].value
        toChests_c = toItems[label][KEY_CHESTS]

        migrated = 0

        # Fill up destination chests, one at a time, until
        # they're all full or all source items have been migrated.
        for (chest, c) in toChests_c:
            # Reload this actual chest.
            (cx, cz) = chunks[c]
            chunk = level.getChunk(cx, cz)
            migrated += migrate_into_chest(chunk, chest, itemsLeft)

        # If all of this label's items have been migrated,
        # update its signs to indicate that.
        if migrated and not itemsLeft:
            signs_c = toItems[label][KEY_SIGNS]
            mark_signs_c_as_migrated(level, chunks, signs_c)

        print(" --> %s migrated, %s." % (
            plural(migrated, "slot"),
            plural(len(itemsLeft), "remain", invert = True)))
        fromItems[label] = nbt.TAG_List(itemsLeft)
        totalMigrated += migrated

    if not totalMigrated:
        print("Nothing was migrated.")
    else:
        print("Saving remaining items to migrate...")
        allData = nbt.TAG_Compound()
        for label in fromItems:
            allData[label] = fromItems[label]
        allData.save(RAW_DATA_FILE)
        print("Saving world...")
        level.saveInPlace()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description =
        'Migrate chests from one Minecraft world to another.')
    parser.add_argument('--from',
        dest = 'copy_from',  metavar = 'WORLD', nargs='*')
    parser.add_argument('--to',
        dest = 'migrate_to', metavar = 'WORLD')
    parser.add_argument('--print-remaining', action='store_true',
        dest = 'print_remaining')

    args = parser.parse_args()

    if args.print_remaining:
        print_remaining_items()
        sys.exit(0)
    elif args.copy_from and args.migrate_to:
        raise Exception('--from and --to must be performed in separate commands.')
    elif not (args.copy_from or args.migrate_to):
        parser.print_help()
        sys.exit(1)

    if args.copy_from:
        copy_from(args.copy_from)
    else:
        migrate_to(args.migrate_to)
