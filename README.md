migrate-chests
==============

A tool for migrating chest contents from one Minecraft world to another.
http://github.com/gmcnew/migrate-chests


## Instructions for players

If you want to create a new [Minecraft](http://minecraft.net) world and keep your hard-earned stockpiles of loot (without painstaking world-editing), now you can!

First, in the old world, for each chest you want to migrate, place a sign within 16 blocks and label it like so:

    > username:keyword

You may use one such sign per chest, or you may use one sign for many chests. You may even use the same keyword for multiple signs.

Then, in the new world, create an empty chest and place an appropriate sign within 16 blocks of it. The sign should be labeled exactly like the corresponding sign in the old world. You may create multiple chests near the sign. When the server admin takes the server offline and runs this script, items items from your old chests will magically appear in your new chests, and "(migrated!)" will appear on your sign. Amazing!

(Note: The script doesn't ensure that the username you put on the sign is actually yours. In fact, it doesn't need to be _anyone's_ username. It's just a convention. The script simply looks for signs with lines matching "string:string".)


## Instructions for server admins

First, collect the contents of properly-labeled chests in the old world:

    > python migrate_chests.py --from path/to/old/world

You may specify multiple worlds:

    > python migrate_chests.py --from path/to/world1 path/to/world2

The old worlds will not be modified &mdash; migrated items are copied, not moved.

Then, periodically migrate items to the new world:

    > python migrate_chests.py --to path/to/new/world

    Loading migration data...
    Loading destination world...
    Examining chunks (100%)...

    Matching 541 chests with 9 migration signs...
    herobrine:base --> 249 slots migrated, 21 remain.
    Saving remaining items to migrate...
    Saving world...

If there are not enough properly-labeled chests for all items to be migrated, a partial migration will occur. You can resume the migration by running the same command.

The ```--print-remaining``` flag shows how many items are left to migrate.


## Special thanks

* [codewarrior0](http://github.com/codewarrior0), whose [pymclevel](http://github.com/codewarrior0/pymclevel) project does about 95% of the hard work for me. =)
