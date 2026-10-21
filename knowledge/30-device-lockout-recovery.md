# Device lockout recovery - official routes only

My AI Pro helps people who are locked out of their OWN devices, using only the
official, legal recovery routes. It never provides FRP-bypass tricks, lock
exploits, password-cracking steps or ways to push software onto phones without
the owner's enrolment - owner policy is defensive-only cybersecurity.

## What FRP actually is

Factory Reset Protection (FRP) is Google's anti-theft lock on Android (5.1+).
After a factory reset, the phone demands the Google account that was last
synced on it. That is the point: a wiped stolen phone is worthless without the
owner's credentials. The same idea exists as Activation Lock on Apple devices.

## If you are locked out of your own phone - official routes

1. **Google account recovery** - https://accounts.google.com/signin/recovery.
   Use your recovery email or phone number; Google walks you back in, then the
   FRP screen accepts those same credentials.
2. **The account already on the phone** - after a reset, enter the Google
   account (and password) that was synced on the device before the reset.
   Forgot the password? Route 1 first, then retry on the phone.
3. **Manufacturer or carrier service with proof of purchase** - Samsung,
   Huawei, Hisense etc. service centres (or your carrier store) will remove a
   lock for the verified purchaser: bring the receipt/box/ID and the IMEI
   (dial *#06# on a working phone, or read it off the box/SIM tray).
4. **Company or school phones (MDM)** - if the device was enrolled by an
   organisation (Google Workspace, Intune, Knox Manage, MDM), the IT admin
   releases or re-enrols it. Ask your admin; that is what MDM exists for.
5. **Second-hand phone with a previous owner's lock** - the seller removes it
   remotely: they sign in at https://android.com/find, choose the device and
   "Remove device" (Apple: icloud.com/find → remove from account). No receipt
   and no seller contact? Treat it as a red flag for a stolen device and take
   it to SAPS rather than paying anyone to "unlock" it.

## Why "FRP bypass" tools and unlock services are a trap

- Most "FRP bypass APKs", "unlock boxes" and YouTube combos deliver **malware**
  or steal the Google/banking credentials you type into them.
- Paid "unlock services" for devices without proof of purchase are usually
  fencing stolen phones - you fund theft and can lose the phone and the money.
- Circumventing access controls on a device you don't own is unlawful access
  (South Africa: Cybercrimes Act 2020; Computer-related offences), and helping
  someone else do it is liability too.

## Stay unlocked - prevention

- Keep recovery email/phone current on every Google/Apple account.
- Before selling or handing on a phone: remove accounts and FRP first
  (Settings → accounts → remove; then factory reset), or remove the device
  remotely from android.com/find / icloud.com/find.
- Note your Google credentials somewhere safe before any reset or repair.
- Business fleets: use proper MDM enrolment with owner consent - it can reset
  and re-provision devices legally, and it is the only sane way to "install
  software to many phones".

## Stolen-device response (defensive)

- Report to SAPS with the IMEI; ask your carrier to blacklist it.
- Use Find My Device / Find My to lock, message or erase remotely.
- Never buy a phone that shows someone else's FRP/Activation lock.

My AI Pro answers lockout questions from this file: official routes,
prevention and safety - and declines bypass/exploit requests politely.
