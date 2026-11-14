//
// C++ Implementation: bot
//
// Description: Main bot code for AssaultCube
//
// Main bot file
//
// Author:  Rick <rickhelmus@gmail.com>
//
//
//

#include "cube.h"
#include "bot.h"

extern int triggertime;
extern itemstat itemstats[];
extern void spawnstate(playerent *d);

//AC Bot class begin

void CACBot::Spawn()
{
    m_pMyEnt->nextprimary = 2 + rnd(5);
    // Keep movement, navigation and squad state initialized in one place.
    CBot::Spawn();
}

void CACBot::CheckItemPickup()
{
    checkitems(m_pMyEnt);
}

// AC Bot class end
