/*jslint browser: true*/ /*global jQuery*/

/**
 * Employee Permissions Access Edit Manager
 *
 * This will manage the client-side validation and manipulations required for the Employee Permissions page to properly
 * function.
 */
(function ($) {

    var accessManager = {

        /**
         * Default constructor
         */
        init: function() {
            // manager local variables
            accessManager.targets = {
                $actionApprovalAuthority: $('#action-approval-authority'),
                $hasActionApprovalAuthority: $('#has-action-approval-authority'),
                $permissionGrant: $('.permission-grant'),
                $permissionOverride: $('.permission-override'),
                $template: $('#template')
            };

            // initialize the event handlers
            this.targets.$actionApprovalAuthority.parent().on('click', this.toggleAllAuthority);
            this.targets.$template.on('change.accessManager.sonnysControls', this.loadFromTemplate);
            this.targets.$permissionGrant.on('change.accessManager.sonnysControls', this.checkOnGrant);
            this.targets.$permissionOverride.on('change.accessManager.sonnysControls', this.updateApprovalAuthority);

            var selectedOption = $('option:selected', this.targets.$template);
            if (selectedOption.val()) {
                // Calling the template function if the user had previously selected it.
                this.targets.$template.trigger('change.accessManager.sonnysControls');
            }
        },

        /**
         * Will load a template definition for the access grants and it's overrides and apply to the current view.
         *
         * @return {void}
         */
        loadFromTemplate: function () {
            var selectedOption = $('option:selected', accessManager.targets.$template);

            // Get the data that will be used for the toggles and cast it to a string to correctly load them
            var permissionSetData = "" + selectedOption.data('permissions-set'),
                managerOverridePermissionSetData = "" + selectedOption.data('manager-override-permissions-set');

            var permissionsSet = null;
            if (permissionSetData.indexOf(',')) {
                permissionsSet = permissionSetData.split(',');
            } else {
                permissionsSet = permissionSetData;
            }

            var managerOverridePermissionSet = null;
            if (managerOverridePermissionSetData.indexOf(',')) {
                managerOverridePermissionSet = managerOverridePermissionSetData.split(',');
            } else {
                managerOverridePermissionSet = managerOverridePermissionSetData;
            }

            // Reset all toggles
            accessManager._resetAllGrantToggles();
            accessManager._resetAllGrantOverrideToggles();

            // Loop through the permissions and enable them
            $.each(permissionsSet, function (index, value) {
                var access = $(accessManager._getIdFromPermissionId(value));
                accessManager._triggerToggle(access, true);
            });

            // Check if there are override grants to be given
            $.each(managerOverridePermissionSet, function (index, value) {
                var override = $(accessManager._getOverrideIdFromPermissionId(value));
                accessManager._triggerToggle(override, true);
            });
        },

        /**
         * Responsible for verifying the state of a given grant toggle and denying or providing access to that action.
         *
         * @param {object} event The event details with the element responsible for triggering it.
         *
         * @return {void}
         */
        checkOnGrant: function (event) {
            var eventTarget = $(event.target),
                id = eventTarget.data('permission-id'),
                overrideElement = $(accessManager._getOverrideIdFromPermissionId(id));

            overrideElement
                .prop('checked', false)
                .bootstrapToggle('update');

            accessManager.updateApprovalAuthority();
        },

        /**
         * Responsible for setting the state of the Action Approval Authority component based on changes on single
         * grant or override permission component.
         *
         * @return {void}
         */
        updateApprovalAuthority: function () {
            var hasAuthority = true;

            accessManager.targets.$permissionGrant.each(function () {
                hasAuthority &= $(this).is(':checked');
            });

            accessManager.targets.$permissionOverride.each(function () {
                hasAuthority &= !$(this).is(':checked');
            });

            accessManager.targets.$hasActionApprovalAuthority.val(hasAuthority);
            accessManager._triggerToggle(accessManager.targets.$actionApprovalAuthority, hasAuthority);
        },

        /**
         * Responsible to set all access permissions to grant and setting the requires manager override to false for
         * all of these accesses.
         *
         * @return {void}
         */
        toggleAllAuthority: function() {
            // Re-queuing the execution since at this point the toggle have not changed yet.
            setTimeout(function () {

                var allAuthority = accessManager.targets.$actionApprovalAuthority.is(':checked');

                accessManager.targets.$hasActionApprovalAuthority.val(allAuthority ? 1 : 0);

                accessManager._setAllGrantPermissionsToggleToState(allAuthority);

                // In all cases Override will be set to false.
                accessManager._resetAllGrantOverrideToggles();

            }, 0);
        },

        /**
         * Responsible for setting a given toggle to a given desired state (on or off).
         *
         * @param {object} toggleOwner The checkbox that is being toggled on or off.
         * @param {boolean} isOn When set to true, will toggle the checkbox to on, when set to false will
         *                       toggle the checkbox off.
         *
         * @private
         *
         * @return {void}
         */
        _triggerToggle: function (toggleOwner, isOn) {
            // triggering the toggle as per documentation - bootstraptoggle.com
            toggleOwner.prop('checked', !!isOn).bootstrapToggle('update');
        },

        /**
         * Responsible for setting all toggles on the permissions page to off.
         *
         * @private
         *
         * @return {void}
         */
        _resetAllGrantToggles: function () {
            // find all toggles of the page and disable them.
            accessManager.targets.$permissionGrant.each(function () {
                accessManager._triggerToggle($(this), false);
            });
        },

        /**
         * Responsible for setting all toggles on the permission overrides page to off.
         *
         * @private
         *
         * @return {void}
         */
        _resetAllGrantOverrideToggles: function () {
            // find all toggles of the page and disable them.
            accessManager.targets.$permissionOverride.each(function () {
                accessManager._triggerToggle($(this), false);
            });
        },

        /**
         * Helper method to convert an permissions id to it's corresponding element id.
         *
         * @param {int} id The permissions id that will be converted to an id select.
         *
         * @private
         *
         * @returns {string}
         */
        _getIdFromPermissionId: function (id) {
            return "#perm-grant-" + id;
        },

        /**
         * Helper method to convert an permissions id to it's corresponding override toggle element id.
         *
         * @param {int} id The permissions id that will be converted to an id select.
         *
         * @private
         *
         * @returns {string}
         */
        _getOverrideIdFromPermissionId: function (id) {
            return "#perm-override-" + id;
        },

        /**
         * Helper method to set the all grant toggles to a given on or off state.
         *
         * @param {boolean} state The state that all toggles will be set to.
         *
         * @private
         *
         * @return {void}
         */
        _setAllGrantPermissionsToggleToState: function(state) {
            accessManager.targets.$permissionGrant.each(function () {
                accessManager._triggerToggle($(this), state);
            });
        }
    };

    // Construct the Manager
    accessManager.init();
})(jQuery);
